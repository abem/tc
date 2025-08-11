#!/bin/bash

# 共通設定の読み込み
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/common.sh"

# デフォルト設定
MODEL="large-v3"
LANGUAGE="ja"
CHUNK_SIZE=100
VERBOSE=false
DEBUG=false

# ヘルプ表示
show_help() {
    cat << EOF
Usage: $(basename "$0") [options]

Options:
    -h, --help          ヘルプを表示
    -v, --verbose       詳細な出力を有効化
    -d, --debug         デバッグモードを有効化
    --model MODEL       Whisperモデルを指定 (default: $MODEL)
    --language LANG     言語を指定 (default: $LANGUAGE)
    --chunk-size SIZE   チャンクサイズを指定 (MB) (default: $CHUNK_SIZE)

Example:
    $(basename "$0") --model large-v3 --language ja
EOF
}

# オプション解析
parse_options() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--verbose)
                VERBOSE=true
                ;;
            -d|--debug)
                DEBUG=true
                set -x
                ;;
            --model)
                MODEL="$2"
                shift
                ;;
            --language)
                LANGUAGE="$2"
                shift
                ;;
            --chunk-size)
                CHUNK_SIZE="$2"
                shift
                ;;
            *)
                log_warning "不明なオプション: $1"
                ;;
        esac
        shift
    done
}

# 前処理
pre_process() {
    log_info "処理を開始します"
    log_info "モデル: $MODEL"
    log_info "言語: $LANGUAGE"
    log_info "チャンクサイズ: ${CHUNK_SIZE}MB"
    
    # 一時ディレクトリの作成
    mkdir -p "$TEMP_DIR"
}

# メイン処理
run_transcription() {
    local start_time=$(date +%s)
    
    # URLの検証
    if [[ -z "${gdrive_url:-}" ]]; then
        handle_error 1 "設定ファイルにURLが指定されていません"
    fi
    
    # Pythonスクリプトの実行
    python3 "${ROOT_DIR}/transcribe_audio.py" \
        "$gdrive_url" \
        --model "$MODEL" \
        --language "$LANGUAGE" \
        --chunk_size "$CHUNK_SIZE" \
        $([ "$VERBOSE" = true ] && echo "--log_level DEBUG") \
        $([ "$DEBUG" = true ] && echo "--debug")
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    log_info "処理時間: ${duration}秒"
}

# 後処理
post_process() {
    # 一時ファイルのクリーンアップ
    cleanup
    log_info "処理が完了しました"
}

# メイン処理
main() {
    # 初期化
    setup_logging
    check_environment
    manage_temp_files
    load_config

    # オプション解析
    parse_options "$@"
    
    # エラーハンドリング
    trap 'handle_error $? "スクリプトが中断されました"' INT TERM
    
    # 処理実行
    pre_process
    run_transcription
    post_process
}

# スクリプト実行
main "$@" 