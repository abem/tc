# (番号未採番・暫定発行): 検査報告書 - YouTube URL処理バグ是正

> **発行日**: 2026年08月02日 / **発行者**: 査ロール(sa) / **文書種別**: 検査報告書
> **検査対象**: `tc`（ブランチ: `feature/fix-youtube-url-routing-2026-08-01`） / **宛先**: 計ロール(kei)
> **注記**: 本案件(tc)では文書番号採番インフラ(00_レビュー依頼/・採番スクリプト・台帳)が未整備のため、計の判断(2026-08-02)により番号なしの暫定発行とする。採番インフラ整備後、計が正式番号を付与する。

## 検査結果

### 判定: **合格**

## 1. 参照資料確認

本案件はAWSリソースを対象としないため、MCP AWS Knowledgeによる公式ドキュメント照合は対象外。代わりに以下を一次資料として直接確認した。

- 対象コード: `tc`（変更後）、`core/cli_workflow.py`（`resolve_input_audio`/`upload_transcription_result`の実装）
- 変更前スナップショット: `backup/20260802_084449/tc_backup`

## 2. 検査項目

| 確認項目 | 結果 | 備考 |
|---------|------|------|
| 差分の正確性(報告値との一致) | ✅ | `git diff --numstat -- tc` = 33 insertions / 48 deletions。作の報告値と完全一致 |
| 構文正当性 | ✅ | `ast.parse` によりコンパイル可能であることを確認 |
| 単体テスト | ✅ | `uv run pytest -q` = 44 passed / 2 skipped / 0 failed（計46件）。作の報告値と完全一致 |
| 実機再現(機能検証) | ✅ | 査自身が `./tc --no-upload` を独立実行し再現(詳細は§3) |
| 削除済み関数の残存参照 | ✅ | `download_from_gdrive`/`upload_to_gdrive` への参照をリポジトリ全体(`.venv`/`__pycache__`除く)で検索し0件を確認 |
| 申し送り事項(gdriveの`is_temp_file`吸収ロジック)の実装確認 | ✅ | `core/cli_workflow.py`のgdrive分岐が`is_temp_file=False`を返す一方、`tc`側で`needs_cleanup = resolution.is_temp_file or resolution.source_type == "gdrive"`として吸収していることをコード直読で確認。従来挙動(gdriveダウンロードファイルの削除)が維持されている |
| 既存オプション挙動の維持 | ✅ | `--no-upload`/`--folder-id`等の引数定義・分岐ロジックに変更が無いことを差分で確認 |
| バックアップの正当性 | ✅ | `diff <(git show HEAD:tc) backup/20260802_084449/tc_backup` で完全一致を確認(変更前の正しいスナップショット) |

## 3. 証拠

### 3.1 差分(numstat)
```
33	48	tc
```

### 3.2 pytest再実行結果(査自身による独立実行)
```
$ uv run pytest -q
...........................ss.................                           [100%]
44 passed, 2 skipped in 1.54s
```

### 3.3 実機再現ログ(査自身による独立実行、`./tc --no-upload`)
```
YouTube URLを検出
... (yt-dlpによるダウンロード、24.58MiB)
Audio extraction complete: output/SUPER-GT-2026-Rd4-富士-監督トークショーGAZOO-Racing_zhfyRQJs6vc.wav
文字起こし開始: モデル=Qwen/Qwen3-ASR-1.7B, 言語=ja, デバイス=cuda
Audio is 1830s (>300s), splitting into chunks for stable processing
... (7チャンク処理、約209.7秒)
Transcription completed: 10447 characters
文字起こし完了: output/20260802_085712_transcription.txt
Temporary file removed: output/SUPER-GT-2026-Rd4-富士-監督トークショーGAZOO-Racing_zhfyRQJs6vc.wav
EXIT_CODE=0
```
文字数(10447文字)・一時ファイル削除・exit 0、いずれも作の完了報告と完全一致。
実行後、`output/*zhfyRQJs6vc*.wav` が存在しないこと(削除済み)を`ls`で直接確認した。

### 3.4 バックアップ照合
```
$ diff <(git show HEAD:tc) backup/20260802_084449/tc_backup && echo "MATCH"
MATCH
```

## 4. 合格判定前の3点自己反証

- **検証範囲**: 差分・構文・単体テスト・実機再現・残存参照検索・バックアップ照合の6系統すべてを査自身が実行して確認した。「主要パターンのみ確認して0件と一般化」していないか——残存参照検索はリポジトリ全体(`.venv`/`__pycache__`除く)を対象に実施しており、範囲限定の問題は無い
- **証拠**: 判定根拠はすべて査自身が直接取得した一次データ(コマンド実行結果・コード直読)であり、作の自己申告(数値・完了報告本文)をそのまま証拠として採用した箇所はない。すべての数値を独立再現し一致を確認した
- **判定**: 検出した不備は§5記載の1件(改善提案)のみであり、合格判定に影響する不備は無い。条件付き合格・保留付き合格は用いていない(二値評価)

## 5. 改善提案(合格判定とは別レイヤー)

作業ツリーに `tc` 以外にも以下の無コミット変更が存在することを確認した。いずれも本タスク(YouTube URL処理バグ是正)の変更範囲には含まれない。

| ファイル | 変更内容 | 本タスクとの関連 |
|---|---|---|
| `config/config.yaml` | gdrive URL → YouTubeテスト用URLへの変更(1 insertion/1 deletion) | テスト実行のための設定変更と推測されるが未確認 |
| `scripts/gpu_monitor.py` | 表示ロジックの修正(7 insertions/9 deletions、herdrペインでの折り返しずれ対策) | 無関係 |

**是正指示ではなく改善提案**: 計がdev反映の際、`git add -A`/`git commit -a`ではなく `git add tc` のように対象ファイルを明示指定し、無関係な変更を巻き込まないこと。判定(合格)そのものへの影響は無い。

## 6. 計ロールへの報告

最終承認およびdevへの反映をお願いする。

**文書終了**
