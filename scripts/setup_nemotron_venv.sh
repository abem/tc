#!/usr/bin/env bash
# Nemotron-3.5-ASR-Streaming 用の隔離venv構築スクリプト(tc-ops #546 Phase2)。
#
# 生産用 .venv には Nemotron が要求する transformers>=5.13.0 をインストールできない
# (qwen-asr が transformers<5 を要求するため衝突する。予備調査で確認済み)。
# そのため本スクリプトは生産用 .venv/pyproject.toml/uv.lock には一切触れず、
# リポジトリ直下 venv-nemotron-poc/ に完全に独立した検証・実行環境を構築する。
#
# バージョンは tc-ops #546 Phase1実測で動作確認済みの組み合わせに明示固定する
# (範囲指定のままだと将来のインストール時に未検証の新バージョンが解決され、
# 再現性が損なわれるリスクがあるため)。
#
# 冪等: venv-nemotron-poc/ が既に存在する場合は何もせず終了する
# (稼働中の検証環境を誤って壊さないため)。再構築したい場合は先に
# `rm -rf venv-nemotron-poc` してから本スクリプトを実行すること。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/venv-nemotron-poc"

if [ -d "${VENV_DIR}" ]; then
  echo "venv-nemotron-poc/ は既に存在します。再構築する場合は先に削除してください: rm -rf ${VENV_DIR}" >&2
  exit 0
fi

cd "${ROOT_DIR}"

uv venv "${VENV_DIR}" --python 3.12

uv pip install --python "${VENV_DIR}/bin/python" \
  "transformers==5.17.0" "torch==2.14.0" --index-url https://download.pytorch.org/whl/cu130 \
  accelerate librosa soundfile

echo "Nemotron隔離venvを構築しました: ${VENV_DIR}"
