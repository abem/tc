# コーディング規約

## 作業開始前の必須事項

過去に、履歴の破壊とテスト未実行が重なり、デグレの対応に 12 時間を費やした事故がありました（`dev` → `main` のマージ時）。
同じ事故を起こさないために、次を作業の前提とします。

- **本規約を冒頭から末尾まで読み、PR の冒頭に「既読・理解済み」と明記する。** 記載のない PR は差し戻す
- **Git 操作**
  - force push・rebase・reset など、履歴を書き換える操作は**絶対禁止**
  - コンフリクトは自力で解決せず、直ちにリード（レビュー担当）へ報告して指示を待つ
  - 指示された操作以外の git 操作はしない（`status` / `log` / `diff` などの参照は可）。push は明示的な指示があるときだけ
  - ブランチの更新順序（feature → dev → main）と main の扱いは `CLAUDE.md` が正本
- **テスト**: コードを変更する前に `uv run python -m pytest tests -q` を全件実行し、緑になるまでコミット・push しない。
  失敗したままのコミットは差し戻す
- **ドキュメントとの同期**: 仕様変更・バグ修正のたびに、関連する README・本規約・コメント・仕様書
  （`docs/spec/00-project-spec.md`）を更新する。未更新の PR は差し戻す
- **CI（自動化されている範囲）**: `.github/workflows/ci.yml` が、push（main / dev / feature/** / fix/** / refactor/**）と
  PR（main / dev 向け）で `uv run ruff check .` と `uv run python -m pytest tests -q` を実行する。
  ドキュメント更新の確認と履歴改変のチェックは自動化されておらず、レビューと運用で確認する。
  自動チェックが失敗したら、作業を止めて原因を直す

この手順を守れない場合は、リードの許可があるまで作業を再開しない。

## 1. 基本方針

### 1.1 コードの品質
- 可読性を最優先する
- 単一責任の原則に従う
- DRY (Don't Repeat Yourself) 原則を守る
- KISS (Keep It Simple, Stupid) 原則を意識する

### 1.2 ドキュメント
- 公開する関数・クラスには docstring を付けることを目標とする（現状は付いていないものもある。新規・変更箇所は付ける）
- 複雑なロジックには適切なコメントを付ける
- README は常に最新の状態を保つ

### 1.3 エラー処理
- 例外は適切に処理する。具体的な例外を捕捉し、握りつぶさない
- ユーザーに見せるメッセージは分かりやすくし、解決のヒントを含める
- 技術的な詳細はログに記録する。ログとラベルは 1 行にする（`core.utils.one_line`。エラー文は 1000 文字まで）

## 2. コーディングスタイル

### 2.1 命名規則
- クラス名: UpperCamelCase（PascalCase）
- 関数名・変数名: snake_case
- 定数: UPPER_SNAKE_CASE
- プライベート変数・関数・メンバー: 先頭にアンダースコア（`_leading_underscore`）

### 2.2 書式
- インデント: 4 スペース
- 行の最大長 120 文字、関数間・クラス間は 2 行空ける。これらは**推奨で、機械では強制していない**。
  ruff の規則は pyflakes 相当の `F`（未使用 import・未定義名など）だけで、整形ツール（formatter）も型チェッカーも導入していない。
  既存コードの書式に合わせる（現状、120 文字を超える行が少数ある）
- lint: `uv run ruff check .`（設定は `pyproject.toml` の `[tool.ruff]` / `[tool.ruff.lint]`）

### 2.3 インポート
- 標準ライブラリ、サードパーティ、ローカルモジュールの順に書く。各グループの間は 1 行空ける
- `from xxx import *` は避ける
- core/ 配下の import を変えるときは、循環 import が起きないか確認する（`CLAUDE.md`）

### 2.4 ドキュメンテーション（docstring）
- 型ヒントを適切に使う
- docstring は Google スタイル（`Args` / `Returns` / `Raises`）を推奨する。現状は日本語の短い説明だけのものが多く、これで足りる

```python
def example_function(param1: str, param2: int) -> bool:
    """関数の説明を記述

    Args:
        param1 (str): 第1引数の説明
        param2 (int): 第2引数の説明

    Returns:
        bool: 戻り値の説明

    Raises:
        ValueError: エラーの説明
    """
    pass
```

## 3. テスト

### 3.1 テストの原則
- 公開 API にはユニットテストを書くことを目標とする（現状は未テストのものがある。例: `UnifiedModelManager`、`SystemConfig`、
  `GDriveClient.find_folder_by_name` / `create_folder`。新規・変更箇所は必ずテストを付ける）
- テストは独立して実行できるようにする。目的の明確なテストケースにする
- 外部依存（モデル・ネットワーク・Google Drive・yt-dlp）はモックを使う。**GPU・ネットワーク・Drive 認証がなくても通ること**
- テストデータは固定値を使い、フィクスチャは再利用可能な形で作る
- 統合テストは主要な機能に対して実装する
- カバレッジは目標 90% 以上。現状は 79%（`uv run python -m pytest tests --cov=core --cov=handlers -q` の TOTAL、2026-10-04 時点）

### 3.2 構造と命名
- ファイル名は `test_` で始める（`tests/` 直下に置く。pytest の探索範囲は `pyproject.toml` の `testpaths = ["tests"]`）
- 関数は `test_<振る舞い>`（例: `test_transcribe_returns_engine_result`）、まとめるクラスは `Test<対象>`
- AAA（Arrange / Act / Assert）の順に書く

```python
def test_something():
    # 1. 準備（Arrange）
    # 2. 実行（Act）
    # 3. 検証（Assert）
```

実行は `uv run python -m pytest tests -q`（`pytest` を直接ではなく、`uv run` 経由で）。

## 4. ロギング

### 4.1 ログレベル
- ERROR: エラー（処理継続不可）
- WARNING: 警告（処理継続可能）
- INFO: 重要な処理の開始・終了
- DEBUG: 詳細なデバッグ情報

### 4.2 フォーマットと設定
- タイムスタンプ・ログレベル・モジュール名・メッセージを出す
- ロガーは `from core.logging import get_logger` で取得する
- `core` は import しただけではログを設定しない。エントリポイント（`tc` / `transcribe.py` / `webui.py` の `main()`）が
  `core.logging.setup_logging()` を呼ぶ（pytest 中は `logs/transcription_test.log`）

## 5. セキュリティ

### 5.1 認証情報
- 認証情報はコードにハードコードしない。環境変数（`.env`）または設定ファイルを使う
- `credentials.json` と `token.pickle` は必ず `.gitignore` に含め、コミットしない
- 保存の実態: `token.pickle` は pickle 形式、`config/config.yaml` は平文。**暗号化はしていない**ので、
  `config.yaml` に機密情報（鍵・トークン）を書かない。ファイルの権限は 600 にする
- パスワードを扱うコードは無いため、パスワードのハッシュ化の規定は該当しない（扱う機能を足すときに定める）

### 5.2 入力検証
- ユーザー入力（URL・ファイル名・アップロード）を検証する。アップロード名は `core.utils.sanitize_upload_filename`
  （最大 200 文字）で無害化する
- SQL はプレースホルダ（`?`）を使い、文字列連結で組み立てない（`core/history.py` を参照）
- ファイルパスと型を検証する

### 5.3 ログ
- 機密情報はログに出力しない
- 適切なログレベルを使い、エラーの詳細情報を記録する

## 6. パフォーマンス

### 6.1 最適化
- 早期最適化は避ける。プロファイリングでボトルネックを特定してから最適化する
- アルゴリズムの効率化、メモリ使用量の最適化は、測定したうえで行う

### 6.2 リソース管理
- メモリリークを防ぎ、リソース（ファイル・一時ファイル・GPU メモリ）は適切に解放する
- キャッシュを効果的に使う（Whisper 系は `core/model_manager.py`）
- 外部コマンド・通信には適切なタイムアウトを付ける（yt-dlp は `--socket-timeout 30`、メタデータ取得 60 秒、出力が 300 秒途絶えると中断）

### 6.3 並列処理
- 重い処理は別スレッドで実行する（WebUI のジョブは同時実行 1 件の逐次処理）
- リソースの競合を避け、エラー処理を確実に実装する

## 7. 認証関連の取り扱い（Google Drive API）

### 7.1 認証ファイル
- `credentials.json` と `token.pickle` は必ず `.gitignore` に含める
- 認証ファイルのバックアップは別の安全な場所に保管する
- 認証ファイルを更新するときは、バックアップ → 新しいファイルの配置 → 動作確認 → バックアップの移動、の順に行う
- 既定の読み書き先は、カレントディレクトリのこの 2 ファイル（`handlers/gdrive_auth.py` の `get_drive_service()`）

### 7.2 更新手順
```bash
# 1. バックアップの作成
cp credentials.json credentials.json.backup
cp token.pickle token.pickle.backup

# 2. 新しい認証ファイルの配置
# credentials.jsonを新しいものに置き換え

# 3. 動作確認（設定読み込み・入力解決＝Drive認証とダウンロードまで行い、文字起こしはしない）
./tc --dry-run "テスト用のGoogle Drive URL"

# 4. バックアップの移動
mv credentials.json.backup /path/to/secure/backup/
mv token.pickle.backup /path/to/secure/backup/
```

### 7.3 トラブルシューティング
認証エラーが発生した場合:
1. バックアップから認証ファイルを復元する
2. 認証ファイルの権限を確認する（600）
3. 必要に応じて認証を再実行する

## 8. バージョン管理

### 8.1 コミット
- 目的ごとに小さなコミットにする（1 つの機能変更につき 1 つのコミット）。性質の異なる変更を 1 つに束ねない
- メッセージは変更内容・理由・影響範囲を具体的に書く。関連する Issue / チケット番号を付ける（`(tc-ops #NNN)`）
- 不要なファイル（`*.bak`、`*.tmp`、認証ファイル）はコミットしない

### 8.2 ブランチ戦略
- `main`: 本番用。**ユーザーの明示的な指示なしに更新しない**
- `dev`: 統合用。本番（tc-prod）が追従するため、dev の更新は本番コードの更新になる。feature/* → dev → main の順で更新する（`CLAUDE.md`）
- `feature/*`: 機能開発用
- `fix/*`: バグ修正用
- `refactor/*`: リファクタリング用
- `docs/*`: ドキュメント更新用

### 8.3 プルリクエスト
- レビュー前にセルフレビューを行う
- テストがすべて通過し、本規約に準拠していることを確認する
- 向け先は `dev`

## 9. デプロイメント・リリース

- feature → dev → main の統合・push・WebUI の再起動は `scripts/release_dev_main.sh` で行う
  （使い方・止まる条件・復旧は [docs/system-docs/release_operations.md](../system-docs/release_operations.md)）
- 統合の前に、テストの実行と変更内容の確認を行う。WebUI のジョブがあるときは再起動しない
- 環境変数・依存関係（`pyproject.toml` / `uv.lock`）・設定ファイルは、変更前にバックアップを取り、段階的に変える

## 10. メンテナンス

### 10.1 コードレビュー
- 機能・セキュリティ・パフォーマンスを確認する

### 10.2 ドキュメント更新
- README・コメント・変更履歴（`CHANGELOG.md`）を更新する
- 変更履歴には、変更内容・変更理由・影響範囲を書く

## 11. ファイル管理

### 11.1 文字起こしファイルの管理
- 文字起こしファイルは `output/` ディレクトリに保存（`tc` は `--output-dir` で変更できる）
- ファイル名のフォーマット: `YYYYMMDD_HHMMSS_transcription.txt`（`core/cli_common.py` の `build_output_file()`）
- 変換履歴は `output/history.db`（SQLite）に記録され、結果テキストも含む
- WebUI は、アップロードされたファイルを `output/uploads/<一意>/<ファイル名>`（同名でも上書きしない。
  7 日を過ぎたものは新しい投入のたびに削除される。`core/housekeeping.py`）、URL入力のダウンロードを
  `output/queue_downloads/<トークン>/` に置く（残った空ディレクトリや部分ファイルは 1 日で削除される）
- `output/` と `logs/` は `.gitignore` の対象（コミットしない）

### 11.2 ファイル命名規則
- 日時ベース（現行）: `YYYYMMDD_HHMMSS_transcription.txt`
- 同一秒に複数の結果を保存する場合は上書きに注意する（`build_output_file()` は秒単位）

### 11.3 クリーンアップ手順
文字起こし結果（`output/*_transcription.txt`）と `output/history.db` は自動削除しない
（WebUI の履歴タブにある「古い履歴の一括削除」は `output/history.db` の行だけを消す）。
自動で整理されるのは、WebUI の `output/uploads`（7 日）と `output/queue_downloads`（1 日）だけである。
手動で整理する場合は、削除前に対象を必ず確認する。

```bash
# 1. 30日以上前の文字起こしファイルを確認（まず一覧だけ。削除しない）
find output -maxdepth 1 -name "*_transcription.txt" -mtime +30

# 2. 一覧を確認してから、必要なものだけ手動で削除またはバックアップへ移動する
```

### 11.4 バックアップ
- 重要な文字起こしファイルは定期的にバックアップする
- 入力が Google Drive / YouTube の場合、結果は Google Drive にもアップロードされる
  （X(twitter) は対象外。`tc` は `--no-upload` でスキップできる。WebUI にスキップの設定は無い）
- `output/history.db` には結果テキストも入っているため、必要に応じてファイルごとバックアップする
