import atexit
import math
import os
import shutil
import tempfile
import struct
import wave
from pathlib import Path

import pytest

# テストが実リポジトリの output/(履歴DB・保存先)に書き込まないよう、core を読み込む前に一時ディレクトリへ向ける。
_TEST_OUTPUT_DIR = tempfile.mkdtemp(prefix="tc-test-output-")
os.environ["TC_OUTPUT_DIR"] = _TEST_OUTPUT_DIR
atexit.register(shutil.rmtree, _TEST_OUTPUT_DIR, ignore_errors=True)

SAMPLE_WAV = Path(__file__).resolve().parents[1] / "samples" / "e2e_sample.wav"


@pytest.fixture(scope="session", autouse=True)
def e2e_sample_wav() -> Path:
    """samples/e2e_sample.wav(git管理外の合成音声)を、全テストより前に用意する。

    複数のテストモジュールがこのパスを直接参照する。以前は test_e2e_dry_run.py だけが
    生成していたため、クリーンな checkout では先に実行されるテストが
    FileNotFoundError になっていた(tc-ops #567 Task 2.0)。
    """
    if not SAMPLE_WAV.exists():
        SAMPLE_WAV.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 16000
        seconds = 1.0
        frequency = 440.0
        amplitude = 0.2
        n_samples = int(sample_rate * seconds)

        with wave.open(str(SAMPLE_WAV), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            for i in range(n_samples):
                t = i / sample_rate
                value = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * t))
                wf.writeframes(struct.pack("<h", value))
    return SAMPLE_WAV


def redirect_output(monkeypatch, base) -> Path:
    """`chdir(base)` して `output/` を base 配下へ向ける(出力先がカレントディレクトリ基準だった頃のテスト用)。

    出力先は core.paths.OUTPUT_DIR(リポジトリ直下)に固定されたため、各モジュールが持つ定数も差し替える。
    """
    import transcribe
    import webui
    from core import cli_workflow

    base = Path(base)
    out = base / "output"
    monkeypatch.chdir(base)
    monkeypatch.setattr(webui, "OUTPUT_DIR", out)
    monkeypatch.setattr(webui, "UPLOAD_DIR", out / "uploads")
    monkeypatch.setattr(webui, "DOWNLOAD_DIR", out / "queue_downloads")
    monkeypatch.setattr(transcribe, "OUTPUT_DIR", out)
    monkeypatch.setattr(cli_workflow, "DEFAULT_HISTORY_DB_PATH", out / "history.db")
    return out
