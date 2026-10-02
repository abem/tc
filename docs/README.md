# 📚 Documentation Index - transcribe_audio

実装の現状に合わせた文書の索引です。記載内容と実装が食い違う場合は、実装(コード)を正とし、文書側を直してください。

## 📖 User Guides
利用者向け(`docs/user-guides/`):

- **[🚀 Tutorial](user-guides/TUTORIAL.md)** - 初めての文字起こし
- **[🔧 Configuration](user-guides/configuration.md)** - 設定リファレンス
- **[🆘 Troubleshooting](user-guides/TROUBLESHOOTING.md)** - 困ったとき
- **[🌐 Language Support](user-guides/language_support_guide.md)** - 言語とエンジンごとの扱い
- **[💻 Modern CLI Usage](user-guides/new_cli_usage.md)** - `tc` / `transcribe.py` の使い方

## 👨‍💻 Developer Guides
開発者向け(`docs/developer-guides/`):

- **[🔌 API Reference](developer-guides/API.md)** - 公開 API
- **[📋 Coding Standards](developer-guides/coding_standards.md)** - 開発指針

リポジトリ直下の `CONTRIBUTING.md`、`DEVELOPMENT.md`、`DEVELOPMENT_QUICKREF.md` も参照してください。

## 🔧 System / Feature Documentation
- **[📊 System Overview](system-docs/system_overview_2025.md)** - システム構成
- **[🖥️ WebUI Architecture](system-docs/webui_architecture.md)** - WebUI の構成と運用
- **[⏱️ Timestamp Feature](feature/timestamp_feature.md)** - タイムスタンプ機能

## 📜 Historical Records
過去の状態を記録した文書です(現行の手順としては使わないでください):

- `historical-records/` - 変更履歴、障害報告、設計の経緯、2025年7月時点の状態(`current_status_2025_july.md`)、依存関係の移行記録(`dependency_migration.md`)
- `REFACTORING_LOG.md` - 2026年3月のリファクタリング履歴
- `INVESTIGATION_REPORT.md` - 調査報告
- `notebooklm/` - 運用の要約と NotebookLM とのやりとりの記録
- `kaizen/` - 改善提案
- `obsolete/` - 廃止した文書(`optimization_features.md` を含む)
