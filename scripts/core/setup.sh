#!/bin/bash

# 共通設定の読み込み
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/common.sh"

# 仮想環境のセットアップ
setup_venv() {
    log_info "仮想環境をセットアップします"
    
    # 既存の仮想環境を削除
    if [ -d "venv" ]; then
        rm -rf venv
    fi
    
    # 新しい仮想環境を作成
    python3 -m venv venv
    source venv/bin/activate
    
    # pipのアップグレード
    pip install --upgrade pip
    
    # 依存パッケージのインストール
    pip install -r requirements/base.txt
}

# 設定ファイルの作成
create_config() {
    log_info "設定ファイルを作成します"
    
    mkdir -p "$CONFIG_DIR"
    
    # config.yamlの作成
    cat > "${CONFIG_DIR}/config.yaml" << EOF
drive:
  chunk_size: 100
  credentials_path: "credentials.json"
  token_path: "token.pickle"

whisper:
  model: "large-v3"
  language: "ja"
  beam_size: 5
  best_of: 3

logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "transcribe.log"
  max_size: 10485760
  backup_count: 5
EOF
}

# ディレクトリ構造の作成
create_directories() {
    log_info "ディレクトリ構造を作成します"
    
    mkdir -p \
        "$LOG_DIR" \
        "$TEMP_DIR" \
        "$CONFIG_DIR"
}

# Google認証のセットアップ
setup_google_auth() {
    log_info "Google認証をセットアップします"
    
    if [ ! -f "credentials.json" ]; then
        log_error "credentials.jsonが見つかりません"
        log_info "Google Cloud Consoleから認証情報をダウンロードしてください"
        exit 1
    fi
    
    # 認証トークンの作成
    python3 -c "
from gdrive_handler import GDriveHandler
handler = GDriveHandler()
handler.authenticate()
"
}

# メイン処理
main() {
    setup_logging
    log_info "セットアップを開始します"
    
    # 環境チェック
    check_environment
    
    # セットアップ実行
    setup_venv
    create_config
    create_directories
    setup_google_auth
    
    log_info "セットアップが完了しました"
}

# スクリプト実行
main "$@" 