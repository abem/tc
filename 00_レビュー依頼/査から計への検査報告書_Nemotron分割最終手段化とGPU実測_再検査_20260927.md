# 査から計への検査報告書(再検査) - Nemotron分割最終手段化とGPU実測 完了報告(是正版)

> **発行日**: 2026年09月27日 / **発行者**: 査ロール（sa） / **文書種別**: 検査報告書（再検査・最優先）
> **検査対象**: 是正版 `scripts/compare_nemotron_baseline.py`（`sys.path.insert`追加） / **宛先**: 計ロール

## 判定: **合格**

## 1. 前回の不合格根拠が是正されたことの確認（再検査の自己拘束）

`scripts/compare_nemotron_baseline.py`冒頭に`if str(_REPO_ROOT) not in sys.path: sys.path.insert(0, str(_REPO_ROOT))`が追加されていることを確認した（実ファイル）。

**査が独立に再実行して確認**（前回と異なる音声ファイルを用いて再現性を確認。JSUT由来70.2秒音声、saku自身が使用したファイルとは別の候補）:

```
$ .venv/bin/python scripts/compare_nemotron_baseline.py \
    WORK_20260926_220529_phase1/test_audio/candidate3_20sent.wav --language ja --device cuda
[1/2] 基準実行(分割なし)を開始: ...
[1/2] 完了: 382文字
[2/2] 現在の実装での実行を開始
[2/2] 完了: 382文字
PASS: 完全一致
（終了コード0）
```

docstring記載の起動方法（`.venv/bin/python scripts/compare_nemotron_baseline.py <audio_path> ...`、`PYTHONPATH`指定なし）で、前回検出した`ModuleNotFoundError`は発生せず、正しく`PASS`判定に到達することを確認した。`--help`の正常出力も確認した。

## 2. その他

```
$ uv run python -m pytest tests -q
173 passed, 1 skipped
$ git diff --name-only -- .venv pyproject.toml uv.lock | wc -l
0
```

## 3. 計ロールへの報告

最終承認をお願いします。承認後、「WebUI再起動で確認可」を采へ報告する運用でよい。

**文書終了**
