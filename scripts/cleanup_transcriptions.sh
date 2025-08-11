#!/bin/bash

# エラーが発生したら即座に終了
set -e

echo "文字起こしファイルのクリーンアップを開始します..."

# 1. 古いファイルのアーカイブ（30日以上経過）
echo "1. 古いファイルをアーカイブ中..."
find output/transcriptions -maxdepth 1 -name "*.txt" -mtime +30 -exec mv {} output/transcriptions/archive/ \;

# 2. 一時ファイルの削除
echo "2. 一時ファイルを削除中..."
rm -f output/transcriptions/temp/*.txt

# 3. 空ディレクトリの削除
echo "3. 空ディレクトリを削除中..."
find output/transcriptions -type d -empty -delete

# 4. バックアップの作成（毎週日曜日）
if [ "$(date +%u)" = "7" ]; then
    echo "4. 週次バックアップを作成中..."
    backup_name="backup_$(date +%Y%m%d_%H%M).tar.gz"
    tar -czf "output/transcriptions/backup/$backup_name" output/transcriptions/*.txt
fi

echo "✅ クリーンアップが完了しました" 