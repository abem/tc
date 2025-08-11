#!/bin/bash

# 共通設定の読み込み
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/common.sh"

# リソース監視
monitor_resources() {
    while true; do
        # CPU使用率
        cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}')
        
        # メモリ使用量
        memory_usage=$(free -m | awk 'NR==2{printf "%.2f%%", $3*100/$2}')
        
        # ディスク使用量
        disk_usage=$(df -h / | awk 'NR==2{print $5}')
        
        # ログ出力
        log_info "CPU: ${cpu_usage}%, Memory: ${memory_usage}, Disk: ${disk_usage}"
        
        # 警告チェック
        check_warnings "$cpu_usage" "$memory_usage" "$disk_usage"
        
        sleep 60
    done
}

# 警告チェック
check_warnings() {
    local cpu=$1
    local memory=$2
    local disk=$3
    
    # CPU使用率が80%以上
    if (( $(echo "$cpu > 80" | bc -l) )); then
        log_warning "CPU使用率が高いです: ${cpu}%"
    fi
    
    # メモリ使用率が80%以上
    if (( $(echo "${memory%\%} > 80" | bc -l) )); then
        log_warning "メモリ使用率が高いです: ${memory}"
    fi
    
    # ディスク使用率が90%以上
    if (( $(echo "${disk%\%} > 90" | bc -l) )); then
        log_warning "ディスク使用率が高いです: ${disk}"
    fi
}

# メイン処理
main() {
    setup_logging
    log_info "リソース監視を開始します"
    monitor_resources
}

# スクリプト実行
main "$@" 