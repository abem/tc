#!/usr/bin/env python3
"""Nemotron 回帰ゲート比較スクリプト(tc-ops #546「分割最終手段化」是正、2026-09-27)。

基準音声に対し、(a) Nemotronの分割なし実行結果(基準)と、(b) 現在の実装
(`core/nemotron_engine.py`の`CHUNK_THRESHOLD_SEC`・無音区間分割ロジック適用後)
での実行結果を比較し、以下のいずれかを満たすかを判定する:

  (1) 完全一致、または
  (2) 類似度0.98以上(既定閾値、`--similarity-threshold`で変更可)かつ末尾欠落なし

判定結果は終了コードで返す(査sa等がCIやコマンドラインから機械的に判定できるように
するため):

  終了コード 0: 合格(完全一致、または類似度・末尾欠落条件を両方満たす)
  終了コード 1: 不合格(類似度が閾値未満、または末尾欠落を検出)
  終了コード 2: 実行エラー(音声ファイル不在、隔離venv未構築、モデル推論失敗等)

## 類似度の算出方法(重要、査sa実測に基づく)

`difflib.SequenceMatcher`は`autojunk=False`を**明示指定**する。`autojunk`の
既定値(True)では、頻出文字列を自動的に「ノイズ」とみなして無視するヒューリス
ティックが働き、日本語の文章比較では意図しない類似度の変動を招く。査sa実測に
よれば、同一の2テキストで`autojunk`既定値(True)では類似度0.824、
`autojunk=False`では0.897(0.896551724137931)となり、**約7ポイントの差**が
生じることを確認済みである。本スクリプトは常に`autojunk=False`を使う。

## 末尾欠落の判定方法

基準テキストの末尾`tail_fraction`(既定10%、最低`min_tail_chars`文字)を切り出し、
`SequenceMatcher(None, current_text, baseline_tail, autojunk=False)`の
マッチブロック合計長を`baseline_tail`の長さで割った「被覆率」を求める。被覆率が
`--tail-coverage-threshold`(既定0.5)未満であれば、基準の末尾内容が現在の結果に
ほとんど現れていないと判断し「末尾欠落」とする(tc-ops #546で実際に発生した
「末尾チャンクの結果が最終テキストに丸ごと含まれない」事象を検出するための設計)。

## 使い方

    venv-nemotron/bin/python scripts/compare_nemotron_baseline.py \\
        <audio_path> --language ja-JP --device cuda

または生産用.venv経由(`core.nemotron_engine`をimportするため、こちらを推奨):

    .venv/bin/python scripts/compare_nemotron_baseline.py \\
        <audio_path> --language ja --device cuda

査(sa)が今後のNemotron変更(チャンク閾値の再調整・分割ロジックの変更等)を検査
する際は、変更後のブランチで本スクリプトを実行し、終了コード0(合格)を
確認すること。基準音声はtc-ops #546で使用した本番再現用Driveファイル
(取り扱いは既存の采指示に従うこと。ダウンロードのみ・作業後削除等)を推奨するが、
任意の音声ファイルパスを指定できる。
"""
from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VENV_PYTHON = _REPO_ROOT / "venv-nemotron" / "bin" / "python"
_INFER_SCRIPT = _REPO_ROOT / "scripts" / "nemotron_infer.py"

# tc-ops #546是正(査sa指摘、2026-09-27): `python scripts/compare_nemotron_baseline.py`
# 形式(モジュールとしてではなく直接パス起動)では、リポジトリルートが
# `sys.path`へ自動的には入らない。`_run_current_implementation()`は
# `from core.config import ...`のように`core`パッケージをimportするため、
# 明示的に`sys.path`へリポジトリルートを追加しておく必要がある(追加しないと
# docstring記載どおりの起動方法で`ModuleNotFoundError: No module named
# 'core.config'`になる。査sa実機実測で検出・再現確認済み)。
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def compute_similarity(baseline: str, current: str) -> float:
    """`autojunk=False`を明示したdifflib.SequenceMatcherで類似度を算出する。

    査sa実測: 同一の2テキストで`autojunk`既定値(True)では0.824、
    `autojunk=False`では0.897となり、日本語文の比較で約7ポイントの差が生じる
    ことを確認済み。本関数は常に`autojunk=False`を使う。
    """
    return difflib.SequenceMatcher(None, baseline, current, autojunk=False).ratio()


def check_no_trailing_loss(
    baseline: str,
    current: str,
    tail_fraction: float = 0.1,
    min_tail_chars: int = 30,
) -> tuple[float, bool]:
    """基準テキストの末尾が現在の結果にどれだけ現れているか(被覆率)を返す。

    被覆率 = (基準の末尾部分に対する、現在の結果とのマッチブロック合計長) /
             (基準の末尾部分の長さ)

    tc-ops #546で実際に発生した「末尾チャンクの結果が最終テキストに丸ごと
    含まれない」事象(#75・#76、67字の欠落がすべて末尾に集中)を検出するための
    設計。戻り値は`(被覆率, 被覆率がcoverage_threshold以上か)`ではなく
    `(被覆率, bool)`——boolは呼び出し元が閾値判定した結果ではなく、本関数の
    デフォルト閾値(0.5)による判定。閾値を変えたい場合は被覆率の数値を直接使うこと。
    """
    if not baseline:
        return 1.0, True

    tail_len = max(min_tail_chars, int(len(baseline) * tail_fraction))
    tail_len = min(tail_len, len(baseline))
    baseline_tail = baseline[-tail_len:]

    matcher = difflib.SequenceMatcher(None, current, baseline_tail, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    coverage = matched / len(baseline_tail) if baseline_tail else 1.0
    return coverage, coverage >= 0.5


def _run_nemotron_infer_no_split(audio_path: str, language: str, device: str, timeout_sec: float) -> str:
    """`scripts/nemotron_infer.py`を分割なしで直接起動し、基準テキストを得る。

    `core.nemotron_engine`のチャンク分割ロジックを一切経由しない(音声ファイルを
    そのまま1つの引数として渡す)ため、常に「分割なし」の基準結果になる。
    """
    if not _VENV_PYTHON.exists():
        raise RuntimeError(
            f"Nemotron隔離venvが見つかりません: {_VENV_PYTHON}。"
            "scripts/setup_nemotron_venv.sh を実行してください。"
        )

    proc = subprocess.run(
        [str(_VENV_PYTHON), str(_INFER_SCRIPT), str(audio_path), "--language", language, "--device", device],
        capture_output=True, text=True, timeout=timeout_sec,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"基準実行(分割なし)が異常終了しました(code={proc.returncode}): {proc.stderr[-2000:]}")
    data = json.loads(proc.stdout)
    chunk = data["chunks"][0]
    if "error" in chunk:
        raise RuntimeError(f"基準実行(分割なし)がエラーを返しました: {chunk['error']}")
    text = chunk.get("transcription", "")
    return "".join(text) if isinstance(text, list) else text


def _run_current_implementation(audio_path: str, language: str, device: str) -> str:
    """`core.nemotron_engine.NemotronSubprocessEngine`(現在の実装、CHUNK_THRESHOLD_SEC・
    無音区間分割ロジック適用後)を実際に呼び出し、結果テキストを得る。

    生産用`.venv`側から実行することを想定する(`core`パッケージのimportが必要なため)。
    """
    from core.config import TranscriptionConfig
    from core.nemotron_engine import NemotronSubprocessEngine

    config = TranscriptionConfig(model="nvidia/nemotron-3.5-asr-streaming-0.6b", language=language, device=device)
    engine = NemotronSubprocessEngine(config)
    result = engine.transcribe(audio_path)
    return result.text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio_path", help="基準音声ファイルのパス")
    parser.add_argument("--language", default="ja", help="core.config.TranscriptionConfig.language相当(既定: ja)")
    parser.add_argument("--nemotron-language", default=None, help="基準実行(nemotron_infer.py直接起動)へ渡す言語コード(既定: --languageから'ja'->'ja-JP'相当に解決)")
    parser.add_argument("--device", default="cuda", choices=["auto", "cuda", "cpu"], help="推論デバイス(既定: cuda)")
    parser.add_argument("--similarity-threshold", type=float, default=0.98, help="合格とみなす類似度の下限(既定: 0.98)")
    parser.add_argument("--timeout-sec", type=float, default=1800.0, help="基準実行(分割なし)のタイムアウト秒数(既定: 1800)")
    args = parser.parse_args()

    audio_path = args.audio_path
    if not Path(audio_path).exists():
        print(f"ERROR: 音声ファイルが見つかりません: {audio_path}", file=sys.stderr)
        return 2

    # 基準実行への言語コード解決(core.nemotron_engine._resolve_languageと同じ対応表)。
    nemotron_lang = args.nemotron_language
    if nemotron_lang is None:
        nemotron_lang = {"ja": "ja-JP", "en": "en-US"}.get(args.language.lower(), "auto")

    try:
        print(f"[1/2] 基準実行(分割なし)を開始: {audio_path}", file=sys.stderr)
        baseline_text = _run_nemotron_infer_no_split(audio_path, nemotron_lang, args.device, args.timeout_sec)
        print(f"[1/2] 完了: {len(baseline_text)}文字", file=sys.stderr)

        print("[2/2] 現在の実装での実行を開始", file=sys.stderr)
        current_text = _run_current_implementation(audio_path, args.language, args.device)
        print(f"[2/2] 完了: {len(current_text)}文字", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: 実行に失敗しました: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if baseline_text == current_text:
        print("PASS: 完全一致")
        return 0

    similarity = compute_similarity(baseline_text, current_text)
    tail_coverage, tail_ok = check_no_trailing_loss(baseline_text, current_text)

    print(f"baseline_len={len(baseline_text)} current_len={len(current_text)}")
    print(f"similarity={similarity:.6f} (autojunk=False, threshold={args.similarity_threshold})")
    print(f"tail_coverage={tail_coverage:.6f} (threshold=0.5)")

    if similarity >= args.similarity_threshold and tail_ok:
        print("PASS: 類似度・末尾欠落チェックとも条件を満たしました")
        return 0

    print("FAIL:", end=" ")
    reasons = []
    if similarity < args.similarity_threshold:
        reasons.append(f"類似度{similarity:.4f}が閾値{args.similarity_threshold}未満")
    if not tail_ok:
        reasons.append(f"末尾欠落の疑い(tail_coverage={tail_coverage:.4f} < 0.5)")
    print("、".join(reasons))
    return 1


if __name__ == "__main__":
    sys.exit(main())
