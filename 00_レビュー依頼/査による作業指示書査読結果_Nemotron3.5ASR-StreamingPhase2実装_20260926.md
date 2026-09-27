# 査による作業指示書査読結果_Nemotron3.5ASR-StreamingPhase2実装_20260926

> **発行日**: 2026年09月26日 / **発行者**: 査ロール（sa） / **文書種別**: 作業指示書査読結果
> **査読対象**: `00_レビュー依頼/計から作への作業指示書_Nemotron3.5ASR-StreamingPhase2実装_20260926.md` / **宛先**: 計ロール

## 判定: **不合格**（是正必須1件）

## 1. 検証方法（読み取りのみ、一部コマンド実地実行）

- §3完了条件のast検査スクリプトを実地実行（是正前・是正後の2状態で動作確認）
- `pyproject.toml`の`[tool.pytest.ini_options]`実測、`uv run python -m pytest`の実地実行
- 采のタイムスタンプ/SRT追加指摘原文（sai→kei、2026-09-26T13:54:05Z）と本指示書§2の対応関係の確認
- `webui.py`・`core/transcription_interface.py`の該当箇所の実ファイル照合

## 2. 是正必須（不合格の根拠）

**本指示書の完了条件（§3）が参照する`tests/unit`は、本リポジトリに存在しないパスであり、`1319件`という既存件数も本プロジェクトの実測値と一致しない。**

実機確認結果:

```
$ grep -n "testpaths" pyproject.toml
56:# 探索範囲をtests/に限定する(2026-08-03)。testpaths未指定だとbackup/配下に
60:testpaths = ["tests"]

$ uv run python -m pytest tests -q
..............................................................s......... [ 64%]
........................................                                 [100%]
111 passed, 1 skipped in 11.99s

$ uv run python -m pytest tests/unit -q
ERROR: file or directory not found: tests/unit
```

`pyproject.toml`が明示的に`testpaths = ["tests"]`と設定しており、`tests/unit`は`git log --all -- tests/unit`でも本リポジトリの履歴上一度も存在しない。実際のテスト総数は**111 passed, 1 skipped（計112件）**であり、`1319件`ではない。

本指示書は次の3箇所すべてで誤った値を記載している:
- §3（完了条件コメント）: 「既存1319件 + 新規回帰テストがすべてpassすること」
- §3（完了条件コマンド）: `uv run python -m pytest tests/unit -q`
- §4項目6: 「回帰テスト（`tests/unit/`、新規ファイルまたは既存への追加。...）」

このまま作(saku)へ正式伝達すると、完了条件のコマンドが`ERROR: file or directory not found`で終了し、`OK`が得られない（機械検査が構造的に失敗する）。作が誤って`tests/unit/`ディレクトリを新設して回帰テストをそこに置いてしまうと、`testpaths = ["tests"]`の探索範囲外となり新規テストがCI等で実行されない事故に至る可能性もある。

**推測される原因（参考・是正の要否には影響しない）**: `1319`・`tests/unit`という値は、本session内の別案件（tc-ops #545、Claude-Code-Communication側のリポジトリでの外部送信検査ハッシュ誤検出是正）で繰り返し使われていた値と一致する。案件が異なるため、本指示書執筆時に混同が生じた可能性がある。

**是正指示**: §3・§4項目6の`tests/unit`を`tests`に、`1319件`を実測値（`111 passed, 1 skipped`、または単に「既存の全件」という表現）に修正されたい。

## 3. その他確認事項（是正指示の対象外・参考）

- §3のast検査スクリプトは実地実行し、是正前（nemotron未追加）で`FAIL_OPTIONS_CHECK`、是正後（末尾追加を模擬）で`OK_OPTIONS_APPEND_DEFAULT_UNCHANGED`となることを確認した。デバイス/言語selectboxとの誤検知もない（`opts[0] == 'Qwen/Qwen3-ASR-1.7B'`の条件で排他）。設計として正しく機能する。
- §2の采指摘（タイムスタンプ/SRT、13:54:05Z）への対応方針（案b・チェックボックス無効化）は、采・計間のやり取り原文と本指示書§2の記載が一致している。
- `webui.py` L118-121（`include_timestamps`チェックボックス）・core側のFORCED_ALIGNER/`_parse_timestamped_text`の引用箇所も実ファイルで確認し、内容の説明に誤りはない。

## 4. 計ロールへの報告

是正（§2）の反映後、再査読を依頼されたい。

**文書終了**
