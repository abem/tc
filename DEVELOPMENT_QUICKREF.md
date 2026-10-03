# 開発者クイックリファレンス

## 🚀 開発開始前チェックリスト

### 環境確認
```bash
# 依存関係がインストール済みか確認 (uv 管理)
uv run python3 -c "import torch; print('✓ torch OK')"

# システム動作確認  
./tc --help

# 設定ファイル確認
uv run python3 -c "from core.config import UnifiedConfig; UnifiedConfig.load(); print('✓ Config OK')"
```

### 安全な作業フロー
1. **ブランチ作成**: `git checkout -b feature/your-feature`
2. **現状把握**: 変更前にシステムをテスト実行
3. **段階的変更**: 小さな変更を積み重ねる
4. **テスト**: 各段階でテスト実行
5. **コミット**: 動作確認できた単位でコミット

## 📁 プロジェクト構造

### 核心コンポーネント(抜粋。全体は DEVELOPMENT.md の「プロジェクト構造」)
```
core/                    # 統一アーキテクチャ（新機能はここに）
├── config.py           # UnifiedConfig（設定統一）
├── logging.py          # 統一ログシステム
├── engine_factory.py   # create_engine（モデル名でエンジンを選ぶ）
├── cli_workflow.py     # 入力解決・finalize_transcription（保存・アップロード・履歴・一時音声の削除）
└── transcription_interface.py  # UnifiedTranscriber（ファサード）

handlers/               # gdrive.py / gdrive_auth.py / youtube.py
tc                      # メインCLI（config/config.yaml 連携、argparse ベース）
transcribe / transcribe.py  # 対話型CLI（transcribe は transcribe.py を起動するシェルラッパー）
webui.py                # WebUI（本番は tc-prod の tc-webui.service。dev を更新すると本番コードが変わる）
```

### 重要な設定
```
config/config.yaml      # システム設定
credentials.json        # Google Drive認証
.venv/                  # 仮想環境 (uv が管理、削除禁止)
```

## 🔧 よく使うコマンド

### 開発・テスト
```bash
# 起動確認(設定読み込み・入力解決までで、文字起こしはしない)
./tc --dry-run "<入力(URLまたはローカルファイルパス)>"

# 基本的な転写(入力は手元で有効なものを使う。テスト用のURLを使い、重要な Drive フォルダでは試さない)
./tc "<入力>" --language ja

# CPU 実行（GPU 問題の切り分け）
./tc "URL" --device cpu

# 開発中の検査
uv run python -m pytest tests -q
uv run ruff check .

# 設定確認 (uv 経由)
uv run python3 -c "from core.config import UnifiedConfig; UnifiedConfig.load(); print(UnifiedConfig.get('whisper'))"
```

### トラブルシューティング
```bash
# 依存関係確認
uv pip list | grep -E "(torch|transformers|google)"

# ログ確認
tail -f logs/transcription.log

# 設定リセット
git checkout config/config.yaml
```

## ⚠️ 危険な操作

### 絶対避けるべき操作
```bash
# これらは実行してはいけません
rm -rf .venv/                # ❌ 仮想環境削除 (uv sync で再作成できるが作業中は避ける)
rm credentials.json          # ❌ 認証情報削除  
rm -rf core/                # ❌ 統一システム削除
git push --force            # ❌ 強制プッシュ
```

### 注意が必要な操作
```bash
# これらは事前確認が必要です
uv remove torch              # ⚠️ pyproject.toml / uv.lock を書き換える。依存関係確認必要
git merge main              # ⚠️ 競合解決準備必要
```

## 🐛 よくある問題と解決法

### ModuleNotFoundError
```bash
# 依存関係が壊れた場合 (uv が pyproject.toml/uv.lock から復元)
uv sync
```

### 転写品質劣化
```bash
# エンジンごとに確認する場所が違う（どのエンジンかは config/config.yaml の whisper.model で決まる）
# Qwen3-ASR（既定）: core/qwen3_engine.py の max_new_tokens（1024）と、core/qwen3_chunking.py の分割処理
# Whisper 系: core/whisper_engine.py の _transcribe_with_original_logic() の max_new_tokens（400）
```

## 📊 品質チェック

出力の確認観点（具体的な数値は、エンジンと設定に依存するため、固定の基準は置かない）:

- 保存形式: `[MM:SS] ` 付きになるのは、Whisper 系（エンジンが 30 秒ごとに付ける）と、
  `include_timestamps: true` のときの Qwen3-ASR（`tc` / WebUI。`transcribe.py` は渡さないので付かない）。
  既定の Qwen3-ASR（`include_timestamps: false`）では付かない
- 欠落の兆候: Qwen3-ASR の `metadata["failed_chunks"]` / `repeated_chunks`（0 が正常）
- 用語: 専門用語が崩れるときは `config/context_hints.txt`（Qwen3-ASR のみ）を確認
- 保存形式・一時ファイルの仕様は [docs/spec/00-project-spec.md](docs/spec/00-project-spec.md)（正本）

## 🚨 緊急時対応

### システム復旧手順
1. **git status** / **git diff** で変更内容確認
2. **./tc --help** で基本動作確認
3. 問題があれば、履歴を書き換える操作（reset / rebase / force push）はせず、リードに報告して指示を待つ
   （戻す場合は、変更を打ち消す新しいコミットを作る。`git revert` は指示を受けてから）

### 重要ファイル復旧
```bash
# .venv 復旧 (uv が pyproject.toml/uv.lock から復元。.venv は削除しない)
uv sync
# それでも直らない場合は、パッケージを入れ直す
uv sync --reinstall

# 設定ファイル復旧
git checkout HEAD -- config/config.yaml
```

## 🔄 統合と WebUI の再起動

- 更新の順序は **feature → dev → main**（個別に更新しない。main の更新はユーザーの明示的な指示があるときだけ）
- dev は本番 tc-prod が追従する。dev の更新は本番コードの更新
- 統合・push・WebUI 再起動は `scripts/release_dev_main.sh <featureブランチ> "<mainのマージメッセージ>"`
  （`--dry-run` で確認だけ。WebUI のジョブがあると止まる）。詳細は
  [docs/system-docs/release_operations.md](docs/system-docs/release_operations.md)

---
*迷った時は CLAUDE.md のべからず集も確認してください（詳細は DEVELOPMENT.md）*