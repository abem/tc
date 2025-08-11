# 開発者クイックリファレンス

## 🚀 開発開始前チェックリスト

### 環境確認
```bash
# 仮想環境が有効か確認
source venv-clean/bin/activate
python3 -c "import torch; print('✓ torch OK')"

# システム動作確認  
./tc --help

# 設定ファイル確認
python3 -c "from core.config import UnifiedConfig; UnifiedConfig.load(); print('✓ Config OK')"
```

### 安全な作業フロー
1. **ブランチ作成**: `git checkout -b feature/your-feature`
2. **現状把握**: 変更前にシステムをテスト実行
3. **段階的変更**: 小さな変更を積み重ねる
4. **テスト**: 各段階でテスト実行
5. **コミット**: 動作確認できた単位でコミット

## 📁 プロジェクト構造

### 核心コンポーネント
```
core/                    # 統一アーキテクチャ（新機能はここに）
├── config.py           # UnifiedConfig（設定統一）
├── logging_config.py   # 統一ログシステム
├── model_manager.py    # モデル管理
└── transcription_interface.py  # 転写インターフェース

transcriber.py          # レガシーだが重要（削除禁止）
tc / transcribe         # 新しいメインエントリーポイント
exec.sh                # レガシーエントリーポイント
main_cli.py             # CLI実装
```

### 重要な設定
```
config/config.yaml      # システム設定
credentials.json        # Google Drive認証
venv-clean/            # 本番仮想環境（削除禁止）
```

## 🔧 よく使うコマンド

### 開発・テスト
```bash
# 基本的な転写テスト
./tc "https://www.youtube.com/watch?v=gjWPtgafPMA" --language ja

# デバッグモード
./tc "URL" --verbose --device cpu

# 設定確認
python3 -c "from core.config import UnifiedConfig; UnifiedConfig.load(); print(UnifiedConfig.get('whisper'))"
```

### トラブルシューティング
```bash
# 依存関係確認
pip list | grep -E "(torch|transformers|google)"

# ログ確認
tail -f logs/transcribe_*.log

# 設定リセット
git checkout config/config.yaml
```

## ⚠️ 危険な操作

### 絶対避けるべき操作
```bash
# これらは実行してはいけません
rm -rf venv-clean/           # ❌ 本番環境削除
rm credentials.json          # ❌ 認証情報削除  
rm -rf core/                # ❌ 統一システム削除
git push --force            # ❌ 強制プッシュ
```

### 注意が必要な操作
```bash
# これらは事前確認が必要です
pip uninstall torch          # ⚠️ 依存関係確認必要
rm *.py.legacy              # ⚠️ 使用状況確認必要
git merge main              # ⚠️ 競合解決準備必要
```

## 🐛 よくある問題と解決法

### ModuleNotFoundError
```bash
# torch関連
source venv-clean/bin/activate
pip install torch transformers

# google関連  
pip install google-api-python-client google-auth
```

### 転写品質劣化
```bash
# 統一システムに問題がある場合
# core/transcription_interface.py の _transcribe_with_original_logic() を確認
# max_new_tokens パラメータを調整（通常400）
```

### 設定エラー
```bash
# AppConfig -> UnifiedConfig移行問題
grep -r "AppConfig" . --include="*.py" --include="*.sh"
# 見つかった箇所をUnifiedConfigに変更
```

## 📊 品質チェック

### 転写品質確認
- 文字数: 4,000文字程度（15分動画）
- タイムスタンプ: `[MM:SS]` 形式で30秒間隔
- 日本語精度: 専門用語も正確に転写

### システム性能確認  
- GPU使用率: 90%以上（CUDA使用時）
- 処理時間: 15分動画を2-3分で処理
- メモリ使用量: 3GB程度（モデル込み）

## 🚨 緊急時対応

### システム復旧手順
1. **git status** で変更内容確認
2. **git stash** で一時的に変更を退避
3. **./tc --help** で基本動作確認
4. 問題があれば **git reset --hard HEAD~1** で前のコミットに戻る

### 重要ファイル復旧
```bash
# venv-clean復旧
python3 -m venv venv-clean
source venv-clean/bin/activate  
pip install torch transformers google-api-python-client

# 設定ファイル復旧
git checkout HEAD -- config/config.yaml
```

---
*迷った時は CLAUDE.md のべからず集も確認してください*