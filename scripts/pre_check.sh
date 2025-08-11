#!/bin/bash

# エラーが発生したら即座に終了
set -e

echo "【最終警告】作業前チェックを開始します"

# 1. テストの実行
echo "1. テストを実行中..."
python -m pytest -v
if [ $? -ne 0 ]; then
    echo "❌ エラー: テストが失敗しました。全テストが通過するまで作業を続行できません。"
    exit 1
fi

# 2. ドキュメントの整合性チェック
echo "2. ドキュメントの整合性をチェック中..."
if ! grep -q "✅ \`coding_standards.md\` を冒頭から末尾まで「完全に」熟読し、理解しました。" .github/PULL_REQUEST_TEMPLATE.md; then
    echo "❌ エラー: PRテンプレートに'既読・理解済み'の宣言がありません"
    exit 1
fi

# 3. コーディング規約の遵守チェック
echo "3. コーディング規約の遵守をチェック中..."
if ! grep -q "coding_standards.md" .github/PULL_REQUEST_TEMPLATE.md; then
    echo "❌ エラー: PRテンプレートにコーディング規約の確認項目がありません"
    exit 1
fi

# 4. ドキュメント更新チェック
echo "4. ドキュメント更新をチェック中..."
if ! git diff --name-only | grep -q "README.md\|docs/"; then
    echo "❌ エラー: ドキュメントの更新が見つかりません。必ず更新してください。"
    exit 1
fi

# 5. Git操作チェック
echo "5. Git操作をチェック中..."
if git log --oneline | grep -q "force\|rebase\|reset"; then
    echo "❌ エラー: 禁止されたGit操作（force push, rebase, reset）が検出されました"
    exit 1
fi

# 6. CI設定チェック
echo "6. CI設定をチェック中..."
if [ ! -f ".github/workflows/ci.yml" ]; then
    echo "❌ エラー: CI設定ファイルが見つかりません"
    exit 1
fi

echo "✅ 全てのチェックが完了しました" 