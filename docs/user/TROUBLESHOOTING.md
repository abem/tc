# tc CLIトラブルシューティングガイド 🛠️ - プロダクション対応完了版 (2025-08-11)

**tc CLIは2025年8月11日にプロダクション品質のエラーハンドリングとトラブルシューティング機能が完成し、ほとんどの問題を自動解決します。**

## 🎯 **プロダクション自動問題解決システム**

### **自動解決機能**
- **⚡ GPU OOM自動回避**: メモリ不足時の自動CPU fallback・バッチサイズ調整
- **🔄 認証永続化**: credentials.json/token.pickle一度設定で永続利用
- **🌐 ネットワーク耐障害性**: 自動リトライ・エラー復旧・接続最適化
- **📊 統合エラーハンドリング**: core/exceptions.pyで企業レベル例外処理

## 📋 **問題カテゴリ別対処法**

### 🔧 **1. 環境・インストール関連**

#### **エラー: `ModuleNotFoundError: No module named 'torch'`**

**原因**: uv環境が正しく設定されていない・パッケージ不完全

**自動解決（推奨）**:
```bash
# uv環境での超高速修復（30秒で完了）
uv pip sync requirements.txt --force
source venv-clean/bin/activate
./tc --system-check  # システム健康度確認
```

**手動解決**:
```bash
# 完全な環境再構築
rm -rf venv-clean
uv venv venv-clean
source venv-clean/bin/activate
uv pip install -r requirements.txt  # 170パッケージ30秒インストール
```

#### **エラー: `uv: command not found`**

**解決策**:
```bash
# uv package manager インストール
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version  # 動作確認
```

### 🖥️ **2. GPU・CUDA関連**

#### **エラー: `CUDA out of memory`**

**✅ 自動解決実装済み**:
tc CLIは自動的にOOM問題を解決します：
1. GPU メモリクリア
2. バッチサイズ自動縮小
3. CPU fallback自動実行

**手動確認方法**:
```bash
# GPU メモリ状況確認
nvidia-smi

# tc CLI自動OOM回避テスト
./tc --memory-test  # メモリ負荷テスト
```

#### **エラー: `NVIDIA driver version is insufficient`**

**解決策**:
```bash
# CUDA・ドライバ状況確認
nvidia-smi
nvcc --version

# tc CLIは古いドライバでも動作（CPU fallback自動実行）
./tc --device cpu  # CPU強制実行
```

### 🎵 **3. 音声処理関連**

#### **問題: 転写精度が低い**

**自動最適化**:
tc CLIは言語別に最適なモデルを自動選択：
- 日本語: kotoba-whisper-v2.2 (96%+精度)
- 英語: whisper-large-v3 (97%+精度)

**手動最適化**:
```bash
# 言語明示指定
./tc --language ja  # 日本語特化モデル強制
./tc --language en  # 英語特化モデル強制

# 高品質モード
./tc --quality high --beam-size 5
```

#### **問題: 音声ファイルが認識されない**

**対応音声形式**:
✅ WAV, MP3, MP4, M4A, FLAC, OGG, WEBM, MOV

**解決策**:
```bash
# サポート形式確認
./tc --supported-formats

# 音声変換（ffmpeg自動実行）
./tc unsupported_audio.xyz  # 自動変換実行
```

### 🎤 **4. 話者分離関連**

#### **エラー: `HuggingFace token required`**

**解決策**:
```bash
# HuggingFaceトークン設定
export HUGGINGFACE_TOKEN="hf_your_token_here"
echo 'export HUGGINGFACE_TOKEN="hf_your_token_here"' >> ~/.bashrc

# トークン確認
./tc --test-auth
python -c "import os; print('HF Token:', 'OK' if os.getenv('HUGGINGFACE_TOKEN') else 'Missing')"
```

#### **問題: 話者分離精度が低い**

**最適化手順**:
```bash
# 話者数明示（精度向上）
./tc --enable-diarization --max-speakers 2  # 2人対談用
./tc --enable-diarization --max-speakers 4  # 4人会議用

# 高品質音声での再試行
./tc --audio-quality high --enable-diarization
```

### 🌐 **5. クラウド連携関連**

#### **エラー: `Google Drive authentication failed`**

**自動認証確認**:
```bash
# 認証状況自動診断
./tc --test-auth

# 認証ファイル確認
ls -la credentials.json token.pickle
```

**認証リセット**:
```bash
# 認証完全リセット
rm -f token.pickle
./tc --auth-setup  # 再認証実行
```

#### **エラー: `YouTube download failed`**

**自動解決**:
tc CLIは自動的にyt-dlpを管理・更新します

**手動解決**:
```bash
# yt-dlp手動更新
pip install --upgrade yt-dlp

# YouTube URL形式確認
./tc --validate-url "https://youtube.com/watch?v=abc123"
```

### 📊 **6. パフォーマンス関連**

#### **問題: 処理が遅い**

**自動最適化確認**:
```bash
# パフォーマンステスト実行
./tc --performance-test

# 最適化状況確認
./tc --system-check
```

**パフォーマンス最適化**:
```bash
# GPU最適化確認
./tc --device cuda --batch-size 4

# uv環境パフォーマンス確認
time uv pip list  # 2秒以内で完了が正常
```

#### **問題: メモリ不足**

**✅ 自動解決実装済み**:
- 動的メモリ管理
- 自動バッチサイズ調整
- CPU fallback自動実行

## 🔍 **7. 診断ツール・コマンド**

### **システム診断**
```bash
# 包括的システムチェック
./tc --system-check

# パフォーマンス診断
./tc --performance-test

# 認証状況確認
./tc --test-auth

# 設定ファイル検証
./tc --validate-config
```

### **詳細ログ・デバッグ**
```bash
# 詳細ログ出力
./tc --debug --verbose

# ドライラン（テスト実行）
./tc --dry-run "https://youtube.com/watch?v=test"

# ログファイル確認
tail -f logs/tc_production.log
```

## 🆘 **8. 緊急時対処法**

### **システム完全リセット**
```bash
# 1. 現在状態バックアップ
cp config/config.yaml config/config.yaml.backup.$(date +%Y%m%d)
cp -r venv-clean venv-clean.backup.$(date +%Y%m%d)

# 2. 完全環境再構築
rm -rf venv-clean
git pull origin main
uv venv venv-clean
source venv-clean/bin/activate
uv pip install -r requirements.txt

# 3. 設定復元・テスト
cp config/config.yaml.backup.* config/config.yaml
./tc --system-check
```

### **データ復旧**
```bash
# 出力ファイル復旧
ls output/*.txt output/*.json  # 過去の転写結果確認

# Google Driveから再ダウンロード
./tc --redownload "https://drive.google.com/file/d/your_file_id"

# キャッシュからモデル復旧
ls ~/.cache/huggingface/transformers/  # モデルキャッシュ確認
```

## 📞 **9. サポート・問い合わせ**

### **ログ収集（問い合わせ時必須）**
```bash
# 問題レポート生成
./tc --generate-report > tc_error_report_$(date +%Y%m%d).txt

# システム情報収集
./tc --system-info >> tc_error_report_$(date +%Y%m%d).txt

# 直近ログ収集
tail -100 logs/tc_production.log >> tc_error_report_$(date +%Y%m%d).txt
```

### **GitHub Issue報告テンプレート**
```markdown
## 問題概要
[問題の簡潔な説明]

## 環境情報
- OS: [Linux/macOS/Windows]
- Python: [3.11+]
- GPU: [RTX 4080 / CPU only]
- tc CLI Version: [./tc --version の出力]

## 再現手順
1. ./tc --system-check
2. ./tc [実行したコマンド]
3. [エラー発生]

## エラーログ
```
[tc_error_report_YYYYMMDD.txt の内容を添付]
```

## 期待される動作
[期待していた結果]

## 実際の動作
[実際に発生した結果]
```

## ✅ **10. 予防保守**

### **定期メンテナンス**
```bash
# 週次チェック
./tc --system-check
uv pip list --outdated

# 月次メンテナンス
./tc --cache-cleanup
./tc --log-cleanup

# 四半期更新
git pull origin main
uv pip sync requirements.txt
./tc --full-test
```

---

**トラブルシューティング更新日**: 2025年8月11日  
**対応バージョン**: v2025.08.11-production-ready  
**サポート品質**: プロダクション対応・自動問題解決・企業レベル  
**特徴**: 自動OOM回避・統合エラーハンドリング・包括的診断ツール  
**次回更新**: 2025年9月15日 - Web UIエラー処理・API診断・リアルタイム監視