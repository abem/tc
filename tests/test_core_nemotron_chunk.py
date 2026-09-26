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

    def test_328_seconds_splits_into_two_equal_chunks(self):
        """計指示の具体例: 328秒→164秒×2の均等分割(短い末尾チャンクは生じない)。"""
        from core.nemotron_engine import compute_chunk_boundaries

        boundaries = compute_chunk_boundaries(328)
        assert boundaries == [(0.0, 164.0), (164.0, 328)]
        # 2チャンクとも同じ長さ(164秒)であること
        assert boundaries[0][1] - boundaries[0][0] == pytest.approx(164.0)
        assert boundaries[1][1] - boundaries[1][0] == pytest.approx(164.0)

    def test_620_seconds_splits_into_three_equal_chunks(self):
        """計指示の具体例: 620秒→約206.67秒×3の均等分割。"""
        from core.nemotron_engine import compute_chunk_boundaries

        boundaries = compute_chunk_boundaries(620)
        assert len(boundaries) == 3
        lengths = [e - s for s, e in boundaries]
        for length in lengths:
            assert length == pytest.approx(620 / 3, abs=0.01)

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
        engine = self._make_engine(monkeypatch, fake_duration=650.0)

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

        # 均等分割(tc-ops #546是正): 650秒はceil(650/300)=3本に均等分割される
        # (300+300+50の不均等分割ではない)。
        expected_chunk_len = 650.0 / 3
        assert len(extracted_ranges) == 3
        for i, (s, e) in enumerate(extracted_ranges):
            assert s == pytest.approx(i * expected_chunk_len, abs=0.01)
            assert (e - s) == pytest.approx(expected_chunk_len, abs=0.01)
        assert extracted_ranges[-1][1] == 650.0
        assert len(call_log) == 1  # サブプロセス起動(=モデルロード)は常に1回
        assert call_log[0] == [
            "/tmp/fake_chunk_1.wav", "/tmp/fake_chunk_2.wav", "/tmp/fake_chunk_3.wav",
        ]
        assert result.text == "チャンク1 チャンク2 チャンク3"
        assert result.metadata["chunked"] is True
        assert result.metadata["chunk_count"] == 3
        assert result.metadata["infer_elapsed_sec"] == pytest.approx(3.0)

    def test_328s_equal_division_both_chunk_results_are_included(self, monkeypatch):
        """328秒(計指示の実機検証と同一長)は164秒×2に均等分割され(短い末尾
        チャンクは生じない)、両チャンクの結果が結合後のテキストに含まれること
        を検証する。

        tc-ops #546で「末尾チャンクの結果が最終テキストに含まれない」という報告
        (#75・#76、940字)があった。実機検証(作、実GPU)により、原因は結合処理の
        バグではなく、当時の固定長分割方式(300秒+28秒)で生じた**短い末尾チャンクを
        前方文脈なしで単体推論すると空文字列が返る**Nemotron側の挙動であることを
        特定した(完了報告書D節に詳細記載)。均等分割方式への変更によりこの短い
        末尾チャンク自体が生じなくなるため、本テストはその前提(164秒×2に分割され、
        両チャンクとも中身のあるテキストが結合されること)を自動テスト化する。"""
        engine = self._make_engine(monkeypatch, fake_duration=328.0)

        def _fake_extract(audio_path, start_sec, end_sec):
            return f"/tmp/fake_chunk_{start_sec:.0f}_{end_sec:.0f}.wav"

        extracted_ranges = []

        def _fake_extract_tracking(audio_path, start_sec, end_sec):
            extracted_ranges.append((start_sec, end_sec))
            return _fake_extract(audio_path, start_sec, end_sec)

        def _fake_invoke(audio_paths, total_duration_sec, lang_code, device_arg):
            assert len(audio_paths) == 2
            return {
                "chunks": [
                    {"transcription": "チャンク1(164秒分)のテキスト", "infer_elapsed_sec": 4.5},
                    {"transcription": "チャンク2(164秒分)のテキスト", "infer_elapsed_sec": 4.5},
                ],
                "load_elapsed_sec": 5.02,
            }

        monkeypatch.setattr(engine, "_extract_chunk_wav", staticmethod(_fake_extract_tracking))
        monkeypatch.setattr(engine, "_invoke_subprocess", _fake_invoke)
        monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)

        result = engine.transcribe(SAMPLE_AUDIO)

        # 短い末尾チャンク(旧300秒+28秒)ではなく164秒×2の均等分割であること
        assert extracted_ranges == [(0.0, 164.0), (164.0, 328.0)]
        assert "チャンク1(164秒分)のテキスト" in result.text
        assert "チャンク2(164秒分)のテキスト" in result.text, (
            "末尾チャンクの結果が結合後のテキストから欠落している"
        )
        assert result.metadata["failed_chunks"] == 0
        assert result.metadata["empty_chunks"] == 0
        assert result.metadata["chunk_count"] == 2

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
