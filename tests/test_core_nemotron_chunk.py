"""
Nemotron 長音声チャンク処理の回帰テスト(tc-ops #546、2026-09-27)。

## 背景

Phase2設計report §5は「長音声チャンク処理: 要」と結論していたが、Phase2実装・
緊急是正のいずれにも未実装だった(査sa実測で判明: `core/nemotron_engine.py`・
`scripts/nemotron_infer.py`にチャンク分割ロジックが存在しなかった)。査の線形
外挿再計算により、10分音声でも推定ピークVRAMが総量(16376MiB)を超過する
可能性が高いと判明したため、既存`Qwen3ASREngine`と同じ`CHUNK_THRESHOLD_SEC=300`
秒の閾値でチャンク分割する実装を追加した(GPU実測着手前の前提条件)。

本ファイルは、GPU不要・モデル実実行なしで以下を検証する:
1. `compute_chunk_boundaries()`: 音声長から分割数・各チャンクの開始/終了時刻が
   正しく計算されること(純粋関数)。
2. `NemotronSubprocessEngine.transcribe()`: 閾値超過時に実際に複数回サブ
   プロセスへ相当する呼び出し(`_invoke_subprocess`)が行われ、結果が半角
   スペースで結合されること、チャンク失敗時にプレースホルダが挿入され他の
   チャンク処理が継続されること。いずれもモデル推論・実サブプロセス起動は
   モックで代替する。
"""
from pathlib import Path

import pytest

SAMPLE_AUDIO = str(Path(__file__).parent.parent / "samples" / "e2e_sample.wav")


class TestComputeChunkBoundaries:
    """純粋関数のみを対象(モデル・サブプロセス不使用)。"""

    def test_short_audio_stays_single_chunk(self):
        from core.nemotron_engine import compute_chunk_boundaries

        assert compute_chunk_boundaries(100) == [(0.0, 100)]

    def test_exactly_at_threshold_stays_single_chunk(self):
        """閾値ちょうど(300秒)は分割しないこと(境界値、<=判定)。"""
        from core.nemotron_engine import compute_chunk_boundaries, CHUNK_THRESHOLD_SEC

        assert compute_chunk_boundaries(CHUNK_THRESHOLD_SEC) == [(0.0, CHUNK_THRESHOLD_SEC)]

    def test_just_over_threshold_splits_into_two(self):
        from core.nemotron_engine import compute_chunk_boundaries

        boundaries = compute_chunk_boundaries(301)
        assert boundaries == [(0.0, 300.0), (300.0, 301)]

    def test_multiple_full_chunks(self):
        """900秒(閾値の3倍ちょうど)は3チャンクに均等分割されること。"""
        from core.nemotron_engine import compute_chunk_boundaries

        boundaries = compute_chunk_boundaries(900)
        assert boundaries == [(0.0, 300.0), (300.0, 600.0), (600.0, 900.0)]

    def test_partial_last_chunk(self):
        """650秒は300+300+50の3チャンクになること(端数チャンクの扱い)。"""
        from core.nemotron_engine import compute_chunk_boundaries

        boundaries = compute_chunk_boundaries(650)
        assert boundaries == [(0.0, 300.0), (300.0, 600.0), (600.0, 650)]

    def test_chunks_are_contiguous_and_cover_full_duration(self):
        """任意の音声長で、チャンクが隙間・重複なく全長をカバーすること
        (境界の連続性の一般的な性質を確認)。"""
        from core.nemotron_engine import compute_chunk_boundaries

        for duration in [1, 299, 300, 300.5, 599, 600, 601, 1000, 1800]:
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

    def test_short_audio_does_not_chunk_and_calls_subprocess_once(self, monkeypatch):
        """閾値以下の音声は、既存(チャンク処理導入前)と同じ単一呼び出しのままである
        こと(既存の単一チャンク経路の挙動を壊していないことの回帰確認)。"""
        engine = self._make_engine(monkeypatch, fake_duration=10.0)

        call_log = []

        def _fake_invoke(audio_path_for_subprocess, chunk_duration_sec, lang_code, device_arg):
            call_log.append(audio_path_for_subprocess)
            return {"transcription": "短い音声のテキスト", "audio_duration_sec": 10.0, "infer_elapsed_sec": 0.5}

        monkeypatch.setattr(engine, "_invoke_subprocess", _fake_invoke)

        result = engine.transcribe(SAMPLE_AUDIO)

        assert len(call_log) == 1
        assert call_log[0] == SAMPLE_AUDIO  # チャンク抽出を経由せず元ファイルをそのまま渡す
        assert result.text == "短い音声のテキスト"
        assert result.metadata["chunked"] is False
        assert result.metadata["chunk_count"] == 1

    def test_long_audio_splits_and_joins_with_space(self, monkeypatch):
        """閾値超過の音声は複数回呼び出され、結果が半角スペースで結合されること
        (既存Qwen3ASREngineと同じ境界の単語結合防止パターン)。"""
        engine = self._make_engine(monkeypatch, fake_duration=650.0)

        extracted_ranges = []

        def _fake_extract(audio_path, start_sec, end_sec):
            extracted_ranges.append((start_sec, end_sec))
            return f"/tmp/fake_chunk_{len(extracted_ranges)}.wav"

        call_count = {"n": 0}

        def _fake_invoke(audio_path_for_subprocess, chunk_duration_sec, lang_code, device_arg):
            call_count["n"] += 1
            return {
                "transcription": f"チャンク{call_count['n']}",
                "audio_duration_sec": chunk_duration_sec,
                "infer_elapsed_sec": 1.0,
            }

        monkeypatch.setattr(engine, "_extract_chunk_wav", staticmethod(_fake_extract))
        monkeypatch.setattr(engine, "_invoke_subprocess", _fake_invoke)
        # tempファイル削除(Path.unlink)がfakeパスに対して失敗しないよう許容する。
        monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)

        result = engine.transcribe(SAMPLE_AUDIO)

        assert extracted_ranges == [(0.0, 300.0), (300.0, 600.0), (600.0, 650.0)]
        assert call_count["n"] == 3
        assert result.text == "チャンク1 チャンク2 チャンク3"
        assert result.metadata["chunked"] is True
        assert result.metadata["chunk_count"] == 3
        assert result.metadata["infer_elapsed_sec"] == pytest.approx(3.0)

    def test_one_chunk_failure_inserts_placeholder_and_continues(self, monkeypatch):
        """1チャンクが失敗しても、プレースホルダを挿入して他のチャンクの処理は
        継続されること(既存Qwen3ASREngineの[チャンクN失敗]パターンを踏襲)。"""
        engine = self._make_engine(monkeypatch, fake_duration=650.0)

        monkeypatch.setattr(
            engine, "_extract_chunk_wav", staticmethod(lambda audio_path, s, e: "/tmp/fake_chunk.wav")
        )
        monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)

        call_count = {"n": 0}

        def _fake_invoke(audio_path_for_subprocess, chunk_duration_sec, lang_code, device_arg):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("模擬的なサブプロセス異常終了")
            return {"transcription": f"チャンク{call_count['n']}", "infer_elapsed_sec": 1.0}

        monkeypatch.setattr(engine, "_invoke_subprocess", _fake_invoke)

        result = engine.transcribe(SAMPLE_AUDIO)

        assert call_count["n"] == 3  # 2番目が失敗しても3番目まで継続される
        assert "チャンク1" in result.text
        assert "[チャンク2失敗]" in result.text
        assert "チャンク3" in result.text
