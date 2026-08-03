#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-}"

if [[ -z "${PYTHON}" ]]; then
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON="${ROOT_DIR}/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

SAMPLE_DIR="${ROOT_DIR}/samples"
SAMPLE_WAV="${SAMPLE_DIR}/e2e_sample.wav"

mkdir -p "${SAMPLE_DIR}"

if [[ ! -f "${SAMPLE_WAV}" ]]; then
  "${PYTHON}" - <<'PY'
import wave, struct, math
from pathlib import Path

sample_rate = 16000
seconds = 1.0
frequency = 440.0
amplitude = 0.2
n_samples = int(sample_rate * seconds)

path = Path("samples/e2e_sample.wav")
path.parent.mkdir(parents=True, exist_ok=True)

with wave.open(str(path), "w") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    for i in range(n_samples):
        t = i / sample_rate
        value = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * t))
        wf.writeframes(struct.pack("<h", value))
print(path)
PY
fi

MODE="${E2E_MODE:-dry-run}"

# tc ランチャーは uv 経由で起動する(shebang 参照)。
TC="${ROOT_DIR}/tc"

if [[ "${MODE}" == "full" ]]; then
  # 実変換(ローカルファイル、アップロードなし)
  exec "${TC}" "${SAMPLE_WAV}" --no-upload --device cpu
fi

# dry-run モード: tc の --dry-run オプション(設定読み込み・入力解決までを
# 行い実際の文字起こしは行わない)を使い、GPU/ネットワーク無しで起動確認する。
exec "${TC}" "${SAMPLE_WAV}" --device cpu --dry-run
