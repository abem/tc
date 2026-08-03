import subprocess
import sys
import wave
import struct
import math
from pathlib import Path


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


def test_e2e_dry_run(tmp_path: Path) -> None:
    """tc(現行の推奨エントリポイント)の起動確認をGPU/ネットワーク無しで行う。

    ローカルwavファイルを渡すことで、resolve_input_audio()が
    ネットワーク呼び出し無しに即時解決される経路(core/cli_workflow.py:70-79)
    のみを通り、--dry-runにより実際の文字起こし(モデルロード)前に終了する。
    import順序変更等でランチャー起動自体が壊れていないかを検知する目的。
    """
    root = Path(__file__).resolve().parents[1]
    sample_wav = root / "samples" / "e2e_sample.wav"
    _ensure_sample_wav(sample_wav)

    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(root / "tc"),
        str(sample_wav),
        "--device",
        "cpu",
        "--output-dir",
        str(output_dir),
        "--dry-run",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "ドライラン" in result.stdout
