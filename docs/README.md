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
- **[📊 System Overview](system-docs/system_overview.md)** - システム構成
- **[🖥️ WebUI Architecture](system-docs/webui_architecture.md)** - WebUI の構成と運用
- **[🚢 Release Operations](system-docs/release_operations.md)** - 運用・リリース手順(dev → main の統合、WebUI の再起動)
- **[📐 Project Spec](spec/00-project-spec.md)** - 利用者に見える挙動の正本（保存形式・一時ファイル削除・yt-dlp・進捗表示・アップロード名など。数値は実装の定数と一致を検査）
- **[⏱️ Timestamp Feature](feature/timestamp_feature.md)** - タイムスタンプ機能

## 📁 リポジトリ直下の文書
- [CHANGELOG.md](../CHANGELOG.md) - 変更履歴
- [SECURITY.md](../SECURITY.md) - セキュリティ方針と脆弱性の報告
- [CONTRIBUTING.md](../CONTRIBUTING.md) - 貢献の手順
- [DEVELOPMENT.md](../DEVELOPMENT.md) - 開発環境と開発の進め方
- [DEVELOPMENT_QUICKREF.md](../DEVELOPMENT_QUICKREF.md) - 開発コマンドの早見表
- [Plans.md](../Plans.md) - 作業計画とタスクの状態

## 📜 Historical Records
過去の状態を記録した文書です(現行の手順としては使わないでください):

- [`historical-records/`](historical-records/) - 現行の文書に載せない記録を集めたディレクトリ。次のものを含む:
  - `INVESTIGATION_REPORT.md` - 2026年3月の現状調査・診断レポート
  - `REFACTORING_LOG.md` - 2026年3月のリファクタリング履歴
  - `current_status_2025_july.md` - 2025年7月時点の状態
  - `dependency_migration.md` - 依存関係の移行記録
  - `ccc-tc-project-operations-summary-20260803.md` / `notebooklm-correspondence-log-20260803.md` - ccc 体制の運用記録と NotebookLM とのやりとり
  - `kaizen_proposal.md` - 2025年5月の出力に対する改善案
  - ほか、変更履歴・障害報告・設計の経緯
- [`obsolete/`](obsolete/) - 廃止した文書(Whisper の精度向上計画、AI への相談文書など)

## 図の作り方
- 図の元データは `figures/<名前>.mmd`（Mermaid）と `figures/<名前>.facts.json`（図に出る文字と矢印の一覧）。SVG は検査済みの成果物。
- `scripts/check_figures.sh [名前]` が、検査環境（`~/Projects/claude/explainer-trial`）へ複製して機械検査し、通ったときだけ SVG を書き戻す。
- 検査後に表示される `look at it` の画像を目で見て、文字の折り返し・矢印の向き・文字の大きさを確認する。
- 文書からは `![図の内容を 1 文で](図への相対パス/figures/<名前>.svg)` で参照する。
- ラベルの 1 行は 16 文字程度まで、1 枚あたり 8 要素前後まで。1 つの問いにつき 1 枚。
