# transcribe_audio プロジェクト べからず集

## 🚨 絶対にやってはいけないこと

### Git ブランチ戦略関連（最重要）
- **🔥 feature/hoge → dev → main の更新順序を破るべからず（絶対厳守）**
  - 必ず feature ブランチ → dev → main の順番で更新すること
  - dev と main を個別に feature から直接更新してはいけない
  - この順序を守らないとブランチ履歴が分岐し「X commits ahead/behind」状態になる
  - 一度分岐すると修復に大量の時間とブランチ削除・再作成が必要になる

- **各ブランチに個別にマージ・コミットするべからず**
  - feature/test → dev へマージ後、dev → main へマージする
  - feature/test → main への直接マージは厳禁
  - feature/test → dev と feature/test → main を並行実行するのも厳禁

- **mainブランチを削除するべからず（緊急事態）**
  - **mainブランチの削除は完全に事故であり、絶対に再現してはいけない**
  - mainは本番ブランチのため、削除すると重大な影響がある
  - GitHub上でデフォルトブランチが失われ、リポジトリ状態が不安定になる
  - 今回は緊急対応として実行したが、通常は絶対に行ってはいけない

- **🚫 mainブランチの更新を勝手に行うべからず（絶対厳守）**
  - **ユーザーからの明示的な指示がない限り、mainブランチのローカル/リモート更新は一切禁止**
  - 自動的な判断や「良かれと思って」の更新は絶対に行わない
  - mainブランチは本番環境に直結するため、予期しない更新は重大な事故につながる
  - 更新が必要な場合は必ずユーザーに確認を求める
  - この禁止事項はClaude Codeの動作において最優先で遵守すること

- **ブランチ同期問題が発生した場合の正しい対処**
  - 「This branch is X commits ahead of, Y commits behind feature/test」が表示されたら即座に修復
  - **mainは削除せず**、問題のあるfeature/devブランチのみ削除・再作成する
  - 例: git push origin --delete dev && git checkout feature/test && git checkout -b dev && git push origin dev
  - mainは最後の手段として、他の方法で解決できない場合のみ検討する

### 環境・インフラ関連
- **.venv/ ディレクトリを削除すべからず**
  - uv が管理する本番仮想環境です
  - 削除するとシステム全体が動作不能になります
  - 技術的負債として見えても、実際には重要なファイルの可能性があります

- **credentials.json や token.pickle を削除すべからず**
  - Google Drive API認証に必要です
  - 削除すると認証が無効になります

- **config/ ディレクトリの設定ファイルを軽率に変更すべからず**
  - システム全体の動作に影響します
  - 変更前にバックアップを取ってください

### コード変更関連
- **AppConfig から UnifiedConfig への移行は慎重に行うべし**
  - 既存の参照箇所をすべて特定してから変更する
  - exec.sh などのシェルスクリプト内の参照も忘れずに更新する

- **import文の変更は依存関係を確認してから行うべし**
  - core/ 配下の統一システムへの移行時は特に注意
  - 循環インポートが発生しないか確認する

- **既存のクラス名やメソッド名を変更する際は影響範囲を調査すべし**
  - grep で全ファイルを検索して使用箇所を特定する
  - TranscriptionConfig など複数ファイルで使用されるものは特に注意

### テスト・デプロイ関連
- **本番データで実験すべからず**
  - テスト用のYouTube URLを使用する
  - 重要なGoogle Driveフォルダで実験しない

- **依存関係の大幅な変更は段階的に行うべし**
  - pyproject.toml / uv.lock の全面書き換えは避ける
  - 最小限の依存関係から段階的にインストールする

- **大量のファイルを一括削除する前に使用状況を確認すべし**
  - `find` コマンドで削除対象を事前に確認する
  - `.legacy` や `.deprecated` でも現在使用中の可能性がある

## ✅ 推奨される安全な作業手順

### ファイル削除前の確認手順
1. `grep -r "filename" .` で使用箇所を確認
2. `git log --oneline --follow filename` で変更履歴を確認  
3. 実際にそのファイル/ディレクトリが参照されていないか確認
4. 可能であれば `.bak` で一時的にリネームしてテスト

### 設定変更の安全手順
1. 変更前に現在の動作を確認・記録
2. バックアップファイル作成（`.bak` 拡張子）
3. 変更後にシステム全体をテスト
4. 問題があれば即座にバックアップから復旧

### 大規模リファクタリングの手順
1. 影響範囲の調査と文書化
2. テスト計画の作成
3. 段階的な実装（一度に全て変えない）
4. 各段階でのテストとコミット
5. 問題発生時の即座のロールバック準備

### 参照残存調査とドキュメント修正の規律
（feature/bugfix2026-07-08 の8ラウンドレビューで得た教訓。同じ轍を踏まないための運用ルール。）

1. **残存参照の調査は初手で語彙を広げてリポジトリ全体にかけ、一度で終わらせる**
   - 「参照が残っていないか確認して直す」系タスクでは、前回指摘されたファイルだけではなく
     最初から `grep -rn <キーワード群> .` を **リポジトリ全体**（docs/scripts/ルート直下の `*.py`/`*.sh`/CLAUDE.md 等を問わず）に実行し、結果全件を一度に処理する。
   - 主観的な「アクティブdocs」線引きをしない。明確に除外すべき `.venv`/`__pycache__` 等だけを exclude する。
   - uv/venv 移行系なら、`venv-clean`, `main_cli\.py`, `requirements[-/.]`, `python3\.11`, `pip install`, `pip uninstall`, `^python3? -c`, `python -m pytest` の語彙群を一度にかける。
   - 「網羅した」「0件を確認した」と報告する際は、実際の grep コマンドと対象範囲を明示する。線引きを言語化できないなら網羅できていない。

2. **ドキュメントに「このコマンドで直る」「このオプションを使う」と書く前に対象実装を直接確認する**
   - argparse 定義、pyproject.toml の依存関係、対象クラス/関数の実在をコードから確認してから書く。
   - 「grep 該当0件」は文言の存在確認に過ぎず、記述内容が正しいかは別問題。可能なら実際にコマンドを実行して確認する。
   - 「たぶんこうだろう」で書いた文言はレビューで指摘されるまで気づかれないという前提で行動する。

3. **スクリプト(.sh / shebang付き.py)を含むコミット前に必ず exec bit の mode 変更を機械確認する**
   - `git diff --summary`（または `git status`）で `mode change 100755 => 100644` の有無を必ずチェックする。
   - ファイル編集ツールで shebang を含むファイルを書き換えると exec bit が落ちることがあるため、初手から固定ステップとして組み込む。

4. **依存関係・環境まわりの変更は、性質の異なる変更を別コミットに分ける**
   - バージョン変更 / ライブラリ差し替え / 新規パッケージ追加を1コミットに束ねない。
   - 1コミットにまとめる方が効率的に見えても、後から問題が起きた際の切り分けコストの方が高くつく。

## 🔧 このプロジェクト固有の注意事項

### アーキテクチャ
- **統一システム (core/) が最新**
  - 新機能は core/ 配下に実装
  - 古いファイルとの互換性も考慮

### 重要なディレクトリ・ファイル
- `.venv/`: 本番仮想環境（uv 管理、削除厳禁）
- `config/`: システム設定（変更は慎重に）
- `core/`: 統一アーキテクチャ（新機能の基盤）
  - `core/logging.py`: 統一ロガー（`from core.logging import get_logger`）
  - `core/config.py`: TranscriptionConfig, DiarizationConfig, UnifiedConfig
  - `core/transcription_interface.py`: UnifiedTranscriber（デュアルエンジン: Qwen3ASREngine / WhisperTranscriptionEngine をモデル名で自動切替）
  - `core/utils.py`: URL検出・デバイス解決ユーティリティ
- `handlers/`: 外部サービスハンドラー
  - `handlers/gdrive.py`: GDriveClient（Google Drive操作）
  - `handlers/youtube.py`: YouTubeClient（YouTube音声抽出）
- `transcribe.py` / `tc`: モダンなCLIローダー（推奨）
- `speaker_diarization.py`: 話者分離機能

### 新CLI (transcribe.py / tc コマンド)
- **推奨実行方法**: `./tc` コマンドでシンプル実行
- **デフォルトモデル**: Qwen/Qwen3-ASR-1.7B（最高精度・2026年ベンチマークトップ）
  - モデル名に `qwen3-asr` を含む場合は Qwen3ASREngine、それ以外は WhisperTranscriptionEngine が自動選択
  - 長音声は5分単位でチャンク分割して処理（CUBLASエラー回避）
- **自動設定読み込み**: config.yamlから自動でURL取得
- **同一フォルダアップロード**: 元音声ファイルと同じGoogle Driveフォルダに結果保存
- **警告抑制済み**: transformers、googleapiclient等の不要ログを抑制

### 新しいAPI使用方法

```python
# ロガー
from core.logging import get_logger
logger = get_logger(__name__)

# 設定
from core.config import TranscriptionConfig, DiarizationConfig, UnifiedConfig
config = TranscriptionConfig.for_language("ja", "high")

# 文字起こし
from core.transcription_interface import UnifiedTranscriber
transcriber = UnifiedTranscriber(config)
result = transcriber.transcribe("audio.wav")

# Google Drive操作
from handlers import GDriveClient
client = GDriveClient()
client.download_file(file_id, output_path)

# YouTube音声抽出
from handlers import YouTubeClient
yt_client = YouTubeClient()
audio_path, metadata = yt_client.download_audio(youtube_url)
```

### 削除済みモジュール（参照しないこと）
- `transcriber.py` / `transcriber/`: 削除済み（後継: `core/transcription_interface.py`）
- `logger.py`: 削除済み（後継: `core/logging.py`）
- `gdrive_handler.py`: 削除済み（後継: `handlers/gdrive.py`）
- `youtube_handler.py`: 削除済み（後継: `handlers/youtube.py`）
- `youtube_gdrive_handler.py`: 削除済み（後継: `handlers/gdrive.py`）
- `patterns/`: 削除済み（未使用）
- `exceptions.py`: 削除済み（未使用）
- `utils.py` (ルート): 削除済み（後継: `core/utils.py`）

### モデル・API関連
- Whisperモデルの変更は転写品質に直接影響
- Google Drive API制限に注意（大量アップロード時）
- GPU/CPUの切り替えは環境確認してから

## 📚 参考資料
- システム概要: `docs/system_overview_2025.md`
- 設定方法: `docs/configuration.md`  
- トラブルシューティング: `docs/`配下の各種ドキュメント

## 🎯 重要原則
**「動いているものは触るな、触るなら慎重に」**

## 🧪 テスト自動化ガイドライン

### テストスペシャリストエージェントの活用
Claude Codeには専用のテストスペシャリストサブエージェントが設定されており、包括的なテスト作成と実行を自動化できます。

### テスト作成時の方針
- **カバレッジ目標**: 90%以上のコードカバレッジを目指す
- **テスト種別**: 単体テスト、統合テスト、E2Eテストを適切に使い分ける
- **エッジケース**: 境界値、null値、異常入力を徹底的にカバー

### テストフレームワーク
- **Python**: pytest（このプロジェクトのメイン）
- **JavaScript/TypeScript**: Jest、React Testing Library
- **E2Eテスト**: Playwright（MCP経由で利用可能）

### テスト実行のベストプラクティス
1. **既存テストの確認**
   - `pytest`でPythonテストを実行
   - テスト設定は`pytest.ini`や`setup.cfg`を確認

2. **新規テスト作成時**
   - AAA（Arrange-Act-Assert）パターンを使用
   - 明確で理解しやすいテスト名を付ける
   - モックは最小限に留める

3. **継続的な品質保証**
   - 全てのテストがパスするまでコミットしない
   - フレーキーなテストは即座に修正
   - テスト実行時間を監視（遅いテストは最適化）

### Playwright MCPの活用
E2Eテストが必要な場合、Playwright MCPサーバー経由でブラウザ自動化が可能です。
- ブラウザ操作の自動化
- スクリーンショット取得
- ネットワークリクエストの監視
- 複数タブ/ウィンドウの制御

## 🔄 Git更新とコミットルール

### コミット前の必須チェック
1. **動作確認**: 変更内容が正常に動作することを確認
2. **依存関係**: 他のファイルへの影響がないか確認
3. **統一システム**: core/配下の統一システムを使用しているか確認
4. **設定ファイル**: config/config.yamlとの整合性を確認

### 安全なコミット手順
```bash
# 1. 変更ファイルの確認
git status

# 2. 差分の詳細確認
git diff

# 3. 段階的なステージング（一度に全てコミットしない）
git add <specific-files>

# 4. 意味のあるコミットメッセージ
git commit -m "fix: AppConfigからUnifiedConfigへの移行

- config.pyの廃止されたAppConfig.get()を修正
- UnifiedConfig.get()への置き換えで統一システムに対応
- Google Drive API認証の安定性を向上

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### コミットメッセージの形式
- **prefix**: `fix:`, `feat:`, `refactor:`, `docs:`, `test:`など
- **概要**: 50文字以内で変更内容を簡潔に
- **詳細**: 変更理由と影響範囲を明記
- **Claude Code署名**: 自動生成コミットには署名を追加

### 絶対に避けるべきコミット
- **未テストの変更**: 動作確認していない変更
- **大量の無関係な変更を一括**: ファイルごとに分割する
- **設定ファイルの機密情報**: credentials.jsonやtoken.pickleの誤コミット
- **一時ファイル**: *.bak、*.tmp、テスト用画像ファイルなど

### ブランチ戦略
- **main**: 安定版のみ
- **feature/***: 新機能開発
- **fix/***: バグ修正
- **refactor/***: リファクタリング

### プッシュ前の最終確認
```bash
# 1. ログの確認
git log --oneline -5

# 2. 全体テスト (uv 経由で実行)
uv run python -c "
import core
from core.config import UnifiedConfig
print('✓ Core system check passed')
"

# 3. 重要システムの確認
uv run python -c "from config import get_drive_service; print('✓ Drive service check passed')"
```

---
*このべからず集は実際の事故事例に基づいて作成されています。*
*新しい事故やトラブルがあった場合は、このファイルに追記してください。*