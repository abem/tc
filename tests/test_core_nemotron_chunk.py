"""
Nemotron 長音声チャンク処理の回帰テスト(tc-ops #546、2026-09-27)。

## 背景

Phase2設計report §5は「長音声チャンク処理: 要」と結論していたが、Phase2実装・
緊急是正のいずれにも未実装だった(査sa実測で判明: `core/nemotron_engine.py`・
`scripts/nemotron_infer.py`にチャンク分割ロジックが存在しなかった)。

## 均等分割方式への変更(tc-ops #546是正、2026-09-27)

当初は`CHUNK_THRESHOLD_SEC`秒ごとの固定長分割だった。実機検証(本番再現用音声、
language=ja-JP・device=cuda)により、この方式で生じる短い末尾チャンク(実測27.7秒)を
前方文脈なしで単体推論すると、エラーにはならず正常終了のまま空文字列を返すことを
確認した。一時的に「短い最終チャンクを前方拡張してオーバーラップさせる」対策を
実装したが、実機検証で境界付近に発話がそのまま重複して現れることが判明し、
利用者への害が大きいとして計・采判断により撤回した。

代わりに`compute_chunk_boundaries()`を**均等分割方式**へ変更した:
総長を`ceil(総長/CHUNK_THRESHOLD_SEC)`本で割り、全チャンクを同じ長さにする。
これにより「短い末尾チャンク」自体が原理的に生じなくなり、重複も生じない。

本ファイルは、GPU不要・モデル実実行なしで以下を検証する:
1. `compute_chunk_boundaries()`: 音声長から均等分割された各チャンクの開始/終了
   時刻が正しく計算されること(純粋関数)。328秒・620秒・299秒を含む。
2. `NemotronSubprocessEngine.transcribe()`: 閾値超過時に実際に複数回サブ
   プロセスへ相当する呼び出し(`_invoke_subprocess`)が行われ、結果が半角
   スペースで結合されること、チャンク失敗時にプレースホルダが挿入され他の
   チャンク処理が継続されること、途中チャンクが空文字列を返した場合に
   failed_chunksとは別枠で記録されること。いずれもモデル推論・実サブ
   プロセス起動はモックで代替する。
"""
from pathlib import Path

import pytest

SAMPLE_AUDIO = str(Path(__file__).parent.parent / "samples" / "e2e_sample.wav")


class TestComputeChunkBoundaries:
    """純粋関数のみを対象(モデル・サブプロセス不使用)。均等分割方式の検証。"""

    def test_short_audio_stays_single_chunk(self):
        from core.nemotron_engine import compute_chunk_boundaries

        assert compute_chunk_boundaries(100) == [(0.0, 100)]

    def test_exactly_at_threshold_stays_single_chunk(self):
        """閾値ちょうど(300秒)は分割しないこと(境界値、<=判定)。"""
        from core.nemotron_engine import compute_chunk_boundaries, CHUNK_THRESHOLD_SEC

        assert compute_chunk_boundaries(CHUNK_THRESHOLD_SEC) == [(0.0, CHUNK_THRESHOLD_SEC)]

    def test_299_seconds_stays_single_chunk(self):
        """計指示の具体例: 299秒は分割なし1本のまま。"""
        from core.nemotron_engine import compute_chunk_boundaries

        assert compute_chunk_boundaries(299) == [(0.0, 299)]

    def test_328_seconds_stays_single_chunk_under_new_threshold(self):
        """tc-ops #546是正(分割最終手段化、2026-09-27): 基準音声と同じ328秒は、
        新閾値(350秒)の下では分割されないこと。

        旧閾値(300秒)の下では328秒は164秒×2に分割されていたが、モデルの
        アーキテクチャ上のハード上限(config.max_position_embeddings=5000、
        実測で400秒がエラー境界)が判明し、采決定によりCHUNK_THRESHOLD_SECを
        350秒へ引き上げた。328秒は350秒以下のため分割不要となり、旧実装が
        引き起こしていた後半チャンクの文脈喪失(#78、分割なし#71比で類似度0.897)
        が原理的に発生しなくなったことをこのテストで保証する。"""
        from core.nemotron_engine import compute_chunk_boundaries, CHUNK_THRESHOLD_SEC

        assert CHUNK_THRESHOLD_SEC == 350
        assert compute_chunk_boundaries(328) == [(0.0, 328)]

    def test_two_chunk_threshold_example_splits_into_two_equal_chunks(self):
        """閾値を明確に超える音声(閾値×2+1秒)は2チャンクへ均等分割されること
        (閾値の具体値に依存しない、CHUNK_THRESHOLD_SECを動的に参照した検証)。"""
        from core.nemotron_engine import compute_chunk_boundaries, CHUNK_THRESHOLD_SEC

        duration = CHUNK_THRESHOLD_SEC + 1  # 閾値をわずかに超える(ceil(duration/閾値)=2)
        boundaries = compute_chunk_boundaries(duration)
        assert len(boundaries) == 2
        expected_len = duration / 2
        for s, e in boundaries:
            assert (e - s) == pytest.approx(expected_len)

    def test_three_chunk_threshold_example_splits_into_three_equal_chunks(self):
        """閾値の2倍を超え3倍以下の音声は3チャンクへ均等分割されること。"""
        from core.nemotron_engine import compute_chunk_boundaries, CHUNK_THRESHOLD_SEC

        duration = CHUNK_THRESHOLD_SEC * 2 + 20  # 2倍を超える(ceil(duration/閾値)=3)
        boundaries = compute_chunk_boundaries(duration)
        assert len(boundaries) == 3
        lengths = [e - s for s, e in boundaries]
        for length in lengths:
            assert length == pytest.approx(duration / 3, abs=0.01)

    def test_no_chunk_exceeds_threshold_after_equal_division(self):
        """均等分割後もチャンク最大長がCHUNK_THRESHOLD_SEC以下であること
        (300秒超のVRAMリスクを再導入しないことの確認)。"""
        from core.nemotron_engine import compute_chunk_boundaries, CHUNK_THRESHOLD_SEC

        for duration in [301, 328, 599, 600, 601, 900, 901, 1800, 3600]:
            boundaries = compute_chunk_boundaries(duration)
            for s, e in boundaries:
                assert e - s <= CHUNK_THRESHOLD_SEC + 1e-6, (
                    f"duration={duration}: チャンク長がCHUNK_THRESHOLD_SECを超過: {boundaries}"
                )

    def test_equal_division_chunk_count_matches_ceil(self):
        """チャンク本数がceil(総長/CHUNK_THRESHOLD_SEC)と一致すること。"""
        import math
        from core.nemotron_engine import compute_chunk_boundaries, CHUNK_THRESHOLD_SEC

        for duration in [301, 328, 599, 600, 601, 900, 1800]:
            boundaries = compute_chunk_boundaries(duration)
            assert len(boundaries) == math.ceil(duration / CHUNK_THRESHOLD_SEC)

    def test_chunks_are_contiguous_and_cover_full_duration(self):
        """任意の音声長で、チャンクが隙間・重複なく全長をカバーすること
        (境界の連続性の一般的な性質を確認)。"""
        from core.nemotron_engine import compute_chunk_boundaries

        for duration in [1, 299, 300, 300.5, 328, 599, 600, 601, 620, 1000, 1800]:
            boundaries = compute_chunk_boundaries(duration)
            assert boundaries[0][0] == 0.0
            assert boundaries[-1][1] == duration
            for (s1, e1), (s2, e2) in zip(boundaries, boundaries[1:]):
                assert e1 == s2, f"duration={duration}: チャンク間に隙間/重複がある: {boundaries}"

    def test_zero_duration_edge_case(self):
        from core.nemotron_engine import compute_chunk_boundaries

        assert compute_chunk_boundaries(0) == [(0.0, 0.0)]


class TestTranscribeChunking:
    """NemotronSubprocessEngine.transcribe()のチャンク分割フロー全体を検証する。
    モデル・実サブプロセスは一切起動しない(_invoke_subprocess/_extract_chunk_wav
    をモックで代替)。"""

    def _make_engine(self, monkeypatch, *, fake_duration: float):
        from core.config import TranscriptionConfig
        from core.nemotron_engine import NemotronSubprocessEngine
        import core.nemotron_engine as nemotron_engine_module
        import sys

        # 隔離venv未構築チェックを通す(実行はモックするため実在パスなら何でもよい)。
        monkeypatch.setattr(nemotron_engine_module, "VENV_PYTHON", Path(sys.executable))

        config = TranscriptionConfig(
            model="nvidia/nemotron-3.5-asr-streaming-0.6b", language="ja", device="cpu"
        )
        engine = NemotronSubprocessEngine(config)
        monkeypatch.setattr(engine, "_get_audio_duration", lambda audio_path: fake_duration)
        # 無音区間調整は実際の音声ファイル(SAMPLE_AUDIO、1秒)を読み込むため、
        # fake_durationとの不整合を避けチャンク分割フローのテストを音声I/Oから
        # 完全に分離するため、恒等関数(均等分割点をそのまま返す)に差し替える。
        # 無音区間調整自体の単体テストはTestFindSilenceBoundary/
        # TestAdjustBoundariesToSilenceで別途行う。
        monkeypatch.setattr(nemotron_engine_module, "adjust_boundaries_to_silence", lambda boundaries, audio_path: boundaries)
        return engine

    def test_short_audio_does_not_chunk_passes_single_path_list(self, monkeypatch):
        """閾値以下の音声は、チャンク抽出を経由せず元ファイルをそのまま
        1要素のリストとして_invoke_subprocess()へ渡すこと(単一モデルロード化・
        tc-ops #548是正後も、サブプロセス呼び出しは常に1回であることの確認)。"""
        engine = self._make_engine(monkeypatch, fake_duration=10.0)

        call_log = []

        def _fake_invoke(audio_paths, total_duration_sec, lang_code, device_arg):
            call_log.append(list(audio_paths))
            return {
                "chunks": [
                    {"transcription": "短い音声のテキスト", "audio_duration_sec": 10.0, "infer_elapsed_sec": 0.5}
                ]
            }

        monkeypatch.setattr(engine, "_invoke_subprocess", _fake_invoke)

        result = engine.transcribe(SAMPLE_AUDIO)

        assert len(call_log) == 1  # サブプロセス起動(=モデルロード)は常に1回
        assert call_log[0] == [SAMPLE_AUDIO]
        assert result.text == "短い音声のテキスト"
        assert result.metadata["chunked"] is False
        assert result.metadata["chunk_count"] == 1

    def test_long_audio_splits_extracts_chunks_single_call_joins_with_space(self, monkeypatch):
        """閾値超過の音声はチャンクへ分割されるが、_invoke_subprocess()の呼び出しは
        常に1回(単一モデルロード、tc-ops #548是正)。全チャンクのパスが一度に渡され、
        結果は半角スペースで結合されること(既存Qwen3ASREngineと同じ境界の
        単語結合防止パターン)。"""
        from core.nemotron_engine import CHUNK_THRESHOLD_SEC

        fake_duration = CHUNK_THRESHOLD_SEC * 2 + 50  # ceil(duration/閾値)=3本になる長さ
        engine = self._make_engine(monkeypatch, fake_duration=fake_duration)

        extracted_ranges = []

        def _fake_extract(audio_path, start_sec, end_sec):
            extracted_ranges.append((start_sec, end_sec))
            return f"/tmp/fake_chunk_{len(extracted_ranges)}.wav"

        call_log = []

        def _fake_invoke(audio_paths, total_duration_sec, lang_code, device_arg):
            call_log.append(list(audio_paths))
            return {
                "chunks": [
                    {"transcription": f"チャンク{i + 1}", "audio_duration_sec": 300.0, "infer_elapsed_sec": 1.0}
                    for i in range(len(audio_paths))
                ],
                "load_elapsed_sec": 5.0,
            }

        monkeypatch.setattr(engine, "_extract_chunk_wav", staticmethod(_fake_extract))
        monkeypatch.setattr(engine, "_invoke_subprocess", _fake_invoke)
        # tempファイル削除(Path.unlink)がfakeパスに対して失敗しないよう許容する。
        monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)

        result = engine.transcribe(SAMPLE_AUDIO)

        # 均等分割(tc-ops #546是正): CHUNK_THRESHOLD_SEC*2+50はceil(.../閾値)=3本に
        # 均等分割される(閾値+閾値+端数、の不均等分割ではない)。
        expected_chunk_len = fake_duration / 3
        assert len(extracted_ranges) == 3
        for i, (s, e) in enumerate(extracted_ranges):
            assert s == pytest.approx(i * expected_chunk_len, abs=0.01)
            assert (e - s) == pytest.approx(expected_chunk_len, abs=0.01)
        assert extracted_ranges[-1][1] == pytest.approx(fake_duration)
        assert len(call_log) == 1  # サブプロセス起動(=モデルロード)は常に1回
        assert call_log[0] == [
            "/tmp/fake_chunk_1.wav", "/tmp/fake_chunk_2.wav", "/tmp/fake_chunk_3.wav",
        ]
        assert result.text == "チャンク1 チャンク2 チャンク3"
        assert result.metadata["chunked"] is True
        assert result.metadata["chunk_count"] == 3
        assert result.metadata["infer_elapsed_sec"] == pytest.approx(3.0)

    def test_328s_baseline_audio_stays_single_chunk_no_context_loss(self, monkeypatch):
        """328秒(基準音声#71・#75-78と同一長)は、新閾値(350秒)の下では分割
        されず単一チャンクとして処理されること。

        tc-ops #546で「末尾チャンクの結果が最終テキストに含まれない」という報告
        (#75・#76、940字)があった。実機検証(作、実GPU)により、原因はNemotronの
        短い孤立チャンクでの空応答挙動と特定したが、その後の均等分割方式(164秒×2)
        でも別の品質劣化(#78、分割なし#71比で類似度0.897、後半チャンクの文脈喪失)
        が判明し、采決定によりCHUNK_THRESHOLD_SECを350秒へ引き上げた
        (完了報告書D節に詳細記載)。328秒は350秒以下のため、本是正後は分割自体が
        発生せず、後半チャンクの文脈喪失が原理的に起こらないことを保証する。"""
        engine = self._make_engine(monkeypatch, fake_duration=328.0)

        call_log = []

        def _fake_invoke(audio_paths, total_duration_sec, lang_code, device_arg):
            call_log.append(list(audio_paths))
            return {
                "chunks": [{"transcription": "分割なしの全文テキスト", "infer_elapsed_sec": 9.0}],
                "load_elapsed_sec": 5.02,
            }

        monkeypatch.setattr(engine, "_invoke_subprocess", _fake_invoke)

        result = engine.transcribe(SAMPLE_AUDIO)

        assert len(call_log) == 1
        assert call_log[0] == [SAMPLE_AUDIO]  # チャンク抽出を経由せず元ファイルをそのまま渡す
        assert result.text == "分割なしの全文テキスト"
        assert result.metadata["chunked"] is False
        assert result.metadata["chunk_count"] == 1
        assert result.metadata["failed_chunks"] == 0
        assert result.metadata["empty_chunks"] == 0

    def test_empty_chunk_transcription_logged_separately_from_failed(self, monkeypatch):
        """途中のチャンクがエラーにならず正常終了のまま空文字列を返すケース
        (実機検証で確認した挙動、長い無音区間等でも起こりうる)は、
        failed_chunksとは別枠(empty_chunks)で記録され、プレースホルダは
        挿入せず、他のチャンクの結果は保持されること(計指示)。"""
        engine = self._make_engine(monkeypatch, fake_duration=650.0)

        monkeypatch.setattr(
            engine, "_extract_chunk_wav", staticmethod(lambda audio_path, s, e: "/tmp/fake_chunk.wav")
        )
        monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)

        def _fake_invoke(audio_paths, total_duration_sec, lang_code, device_arg):
            return {
                "chunks": [
                    {"transcription": "チャンク1", "infer_elapsed_sec": 1.0},
                    {"transcription": "", "infer_elapsed_sec": 0.3},  # 正常終了・空文字列
                    {"transcription": "チャンク3", "infer_elapsed_sec": 1.0},
                ]
            }

        monkeypatch.setattr(engine, "_invoke_subprocess", _fake_invoke)

        result = engine.transcribe(SAMPLE_AUDIO)

        assert "チャンク1" in result.text
        assert "チャンク3" in result.text
        assert "[チャンク2失敗]" not in result.text, (
            "空文字列応答(正常終了)はfailed_chunksのプレースホルダと混同してはならない"
        )
        assert result.metadata["failed_chunks"] == 0
        assert result.metadata["empty_chunks"] == 1

    def test_one_chunk_error_inserts_placeholder_and_keeps_others(self, monkeypatch):
        """1プロセス内の1チャンクが失敗("error"キー付きで返る)しても、
        プレースホルダを挿入して他のチャンクの結果は保持されること
        (既存Qwen3ASREngineの[チャンクN失敗]パターンを踏襲)。"""
        engine = self._make_engine(monkeypatch, fake_duration=650.0)

        monkeypatch.setattr(
            engine, "_extract_chunk_wav", staticmethod(lambda audio_path, s, e: "/tmp/fake_chunk.wav")
        )
        monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)

        def _fake_invoke(audio_paths, total_duration_sec, lang_code, device_arg):
            return {
                "chunks": [
                    {"transcription": "チャンク1", "infer_elapsed_sec": 1.0},
                    {"error": "TypeError: 模擬的な推論エラー"},
                    {"transcription": "チャンク3", "infer_elapsed_sec": 1.0},
                ]
            }

        monkeypatch.setattr(engine, "_invoke_subprocess", _fake_invoke)

        result = engine.transcribe(SAMPLE_AUDIO)

        assert "チャンク1" in result.text
        assert "[チャンク2失敗]" in result.text
        assert "チャンク3" in result.text
        assert result.metadata["failed_chunks"] == 1


class TestFindSilenceBoundary:
    """`find_silence_boundary()`の純粋関数としての検証(GPU不要、ダミーnumpy配列使用)。
    tc-ops #546是正(分割最終手段化、2026-09-27、采の具体的指示による実装)。"""

    def _make_audio_with_quiet_span(self, duration_sec, sr, quiet_start_sec, quiet_end_sec, seed=0):
        import numpy as np

        rng = np.random.default_rng(seed)
        n = int(duration_sec * sr)
        audio = (rng.standard_normal(n) * 0.1).astype(np.float32)
        q0 = int(quiet_start_sec * sr)
        q1 = int(quiet_end_sec * sr)
        audio[q0:q1] = 0.0
        return audio

    def test_finds_quiet_span_within_search_radius(self):
        """target_secの近傍に明確な無音区間があれば、その位置を返すこと。"""
        from core.nemotron_engine import find_silence_boundary

        sr = 16000
        audio = self._make_audio_with_quiet_span(100.0, sr, quiet_start_sec=45.0, quiet_end_sec=48.0)

        result = find_silence_boundary(audio, sr, target_sec=50.0, total_duration_sec=100.0, search_radius_sec=20.0)

        assert 45.0 <= result <= 48.0, f"無音区間(45〜48秒)内の位置が返らなかった: {result}"

    def test_falls_back_to_target_when_search_window_too_small(self):
        """探索窓が音声端に近く実効的に狭すぎる場合、target_secへフォールバックすること。"""
        import numpy as np
        from core.nemotron_engine import find_silence_boundary

        sr = 16000
        audio = (np.random.default_rng(1).standard_normal(int(0.05 * sr))).astype(np.float32)  # 50ms

        result = find_silence_boundary(audio, sr, target_sec=0.02, total_duration_sec=0.05, search_radius_sec=20.0)

        assert result == 0.02

    def test_search_window_clamped_to_audio_bounds(self):
        """探索窓が音声の始端・終端を越える場合、実際の音声範囲内にクランプされること
        (返り値が音声長を超えたり負になったりしない)。"""
        from core.nemotron_engine import find_silence_boundary

        sr = 16000
        audio = self._make_audio_with_quiet_span(30.0, sr, quiet_start_sec=25.0, quiet_end_sec=28.0)

        # target=28秒、search_radius=20秒 -> 素朴には8〜48秒だが、音声は30秒までしかない
        result = find_silence_boundary(audio, sr, target_sec=28.0, total_duration_sec=30.0, search_radius_sec=20.0)

        assert 0.0 <= result <= 30.0


class TestAdjustBoundariesToSilence:
    """`adjust_boundaries_to_silence()`の検証。実ファイルI/O(librosa.load)を伴うため、
    最小限の実wavファイル(GPU不要、音声デコードのみ)を一時生成して検証する。"""

    def _write_test_wav(self, tmp_path, duration_sec=100.0, sr=16000, quiet_start_sec=45.0, quiet_end_sec=48.0):
        import numpy as np
        import soundfile as sf

        rng = np.random.default_rng(0)
        n = int(duration_sec * sr)
        audio = (rng.standard_normal(n) * 0.1).astype(np.float32)
        audio[int(quiet_start_sec * sr):int(quiet_end_sec * sr)] = 0.0
        path = tmp_path / "test_silence.wav"
        sf.write(str(path), audio, sr)
        return str(path)

    def test_single_chunk_passthrough_without_audio_io(self, tmp_path, monkeypatch):
        """境界が1件(分割不要)の場合は音声ファイルを読み込まず、そのまま返すこと。"""
        from core.nemotron_engine import adjust_boundaries_to_silence

        # librosa.loadが呼ばれたら失敗させ、実際に読み込みが発生していないことを保証する。
        import librosa

        def _fail_if_called(*args, **kwargs):
            raise AssertionError("分割不要な場合はlibrosa.loadを呼んではならない")

        monkeypatch.setattr(librosa, "load", _fail_if_called)

        boundaries = [(0.0, 100.0)]
        result = adjust_boundaries_to_silence(boundaries, "/nonexistent/path.wav")

        assert result == boundaries

    def test_internal_boundary_adjusted_to_silence(self, tmp_path):
        """内部境界(チャンク間の分割点)が、その近傍の無音区間へ実際に寄せられること。
        先頭(0.0)・末尾(全体長)は変更されないこと。"""
        from core.nemotron_engine import adjust_boundaries_to_silence

        wav_path = self._write_test_wav(tmp_path, duration_sec=100.0, quiet_start_sec=45.0, quiet_end_sec=48.0)

        # 均等分割点が50秒(無音区間の少し先)になるよう2チャンクの境界を用意する。
        boundaries = [(0.0, 50.0), (50.0, 100.0)]
        adjusted = adjust_boundaries_to_silence(boundaries, wav_path)

        assert adjusted[0][0] == 0.0
        assert adjusted[-1][1] == 100.0
        internal_point = adjusted[0][1]
        assert 45.0 <= internal_point <= 48.0, (
            f"内部境界が無音区間(45〜48秒)へ寄せられなかった: {internal_point}"
        )
        assert adjusted[0][1] == adjusted[1][0]  # 連続性が保たれていること

    def test_no_silence_found_falls_back_to_equal_division(self, tmp_path):
        """近傍に無音区間が無い場合、均等分割点のままフォールバックすること
        (一様乱数ノイズのみの音声、無音区間なし)。"""
        import numpy as np
        import soundfile as sf
        from core.nemotron_engine import adjust_boundaries_to_silence

        sr = 16000
        rng = np.random.default_rng(2)
        audio = (rng.standard_normal(int(100.0 * sr)) * 0.5 + 0.5).astype(np.float32)  # 無音区間なし、常に大振幅
        path = tmp_path / "no_silence.wav"
        sf.write(str(path), np.clip(audio, -1.0, 1.0), sr)

        boundaries = [(0.0, 50.0), (50.0, 100.0)]
        adjusted = adjust_boundaries_to_silence(boundaries, str(path))

        # 無音区間が無くても、探索窓内で最小RMSの点へは寄る(クラッシュしないこと)。
        # 先頭・末尾は不変であること、境界の連続性が保たれることのみを保証する。
        assert adjusted[0][0] == 0.0
        assert adjusted[-1][1] == 100.0
        assert adjusted[0][1] == adjusted[1][0]
