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

# main_cli.py はリファクタリングで削除され tc/transcribe.py に統合済。
# tc ランチャーは uv 経由で起動する(shebang 参照)。
TC="${ROOT_DIR}/tc"

if [[ "${MODE}" == "full" ]]; then
  # 実変換(ローカルファイル、アップロードなし)
  exec "${TC}" "${SAMPLE_WAV}" --no-upload --device cpu
fi

# dry-run モード: 現ランチャー(tc/transcribe.py)は --dry-run をサポートしないため
# 実行不能。E2E テストの再実装は別PRで行う(tests/test_e2e_dry_run.py の skip理由参照)。
echo "[e2e_local] dry-run モードは現在サポートされていません。" >&2
echo "[e2e_local] main_cli.py が削除され --dry-run オプションが現ランチャーに存在しません。" >&2
echo "[e2e_local] full モード(E2E_MODE=full)を使うか、tests/test_e2e_dry_run.py の再実装をお待ちください。" >&2
exit 1
