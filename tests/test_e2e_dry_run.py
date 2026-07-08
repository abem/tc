import subprocess
import sys
import wave
import struct
import math
from pathlib import Path

import pytest


def _ensure_sample_wav(path: Path) -> None:
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16000
    seconds = 1.0
    frequency = 440.0
    amplitude = 0.2
    n_samples = int(sample_rate * seconds)

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            t = i / sample_rate
            value = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * t))
            wf.writeframes(struct.pack("<h", value))


@pytest.mark.skip(
    reason=(
        "main_cli.py はリファクタリングで削除され tc/transcribe.py に統合された。"
        "かつ --dry-run オプションも現ランチャーには存在しないため、"
        "このテストは実態と乖離している。再実装は別PRで行う。"
    )
)
def test_e2e_dry_run(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    sample_wav = root / "samples" / "e2e_sample.wav"
    _ensure_sample_wav(sample_wav)

    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(root / "main_cli.py"),
        str(sample_wav),
        "--language",
        "ja",
        "--model",
        "kotoba-tech/kotoba-whisper-v2.2",
        "--device",
        "cpu",
        "--output-dir",
        str(output_dir),
        "--dry-run",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "ドライラン" in result.stdout
