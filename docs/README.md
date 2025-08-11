# ドキュメント インデックス - 音声文字起こしシステム（tc）

## 🚀 新CLI対応システム

**推奨実行方法**: `./tc` コマンドでシンプル実行  
**環境**: uvパッケージマネージャー推奨（pip比較10倍高速）  
**特徴**: YouTube→Google Drive自動連携、設定ファイル自動読み込み

## 📚 ドキュメント一覧

### 📖 ユーザー向けガイド (user/)
- **[TUTORIAL.md](user/TUTORIAL.md)** - ステップバイステップガイド（uv環境セットアップ〜tc CLI使用方法）
- **[TROUBLESHOOTING.md](user/TROUBLESHOOTING.md)** - tc CLIトラブルシューティング完全版
- **[設定ガイド](user/configuration.md)** - config.yaml自動読み込み・統一設定管理
- **[言語対応ガイド](user/language_support_guide.md)** - 日本語/英語モデル自動選択
- **[話者分離セットアップ](user/speaker_diarization_setup.md)** - pyannote.audio v3.3.2設定

### 👨‍💻 開発者向けガイド (developer/)
- **[API仕様書](developer/API.md)** - tc CLI対応プログラマー向けAPIガイド
- **[tc CLI使用方法](developer/new_cli_usage.md)** - プロダクション品質のモダンCLIシステム
- **[コーディング標準](developer/coding_standards.md)** - 統一システム（core/）コーディング規約
- **[実装変更ログ](developer/implementation_changes.md)** - 技術実装の変更点

### 🏗️ システムドキュメント (system/)
- **[システム概要 2025年版](system/system_overview_2025.md)** - tc CLIシステム全体の機能・技術詳細
- **[最適化機能詳細](system/optimization_features.md)** - uv環境・GPU最適化機能
- **[依存関係移行](system/dependency_migration.md)** - pipからuvへの移行記録
- **[実装ノート](system/implementation_notes.md)** - 開発時の技術メモ

### 📈 計画・設計 (plans/)
- **[計画表](plans/計画表.md)** - プロジェクト全体計画・進捗状況
- **[文脈考慮文字起こし計画](plans/文脈考慮文字起こし実装計画.md)** - 高度機能実装計画
- **[Whisper改善ガイド](plans/whisper_improvement_guide.md)** - 音声認識精度向上計画
- **[Whisper API最適化計画](plans/whisper_api最適化計画書.md)** - APIパフォーマンス最適化
- **[機能別計画](plans/feature/)** - 話者分離・タイムスタンプ機能詳細

### 📈 分析・レポート (reports/)
- **[進捗報告 2025-05-15](reports/進捗報告_20250515.md)** - 詳細な開発進捗チェックリスト
- **[完了状況分析](reports/完了状況分析.md)** - 機能別達成度分析
- **[現在のシステム状況 2025-07](reports/current_status_2025_july.md)** - 2025年7月時点の最新状況
- **[Geminiレビュー結果](reports/gemini_review_4.md)** - AI分析結果・改善提案
- **[変更履歴](reports/change_history.md)** - 機能変更・改善履歴

### 🗄️ 履歴・アーカイブ (archive/)
- 過去の調査レポート、問題解決履歴、改善提案など17ファイル

## 🎯 用途別ドキュメントガイド

### 💻 新規ユーザー向け
1. **[メインREADME](../README.md)** - uv環境セットアップ、tc CLI基本使用方法
2. **[初心者チュートリアル](user/TUTORIAL.md)** - ステップバイステップガイド
3. **[tc CLI使用方法](developer/new_cli_usage.md)** - プロダクションCLI詳細使用方法

### 🎤 話者分離機能利用者向け
1. **[話者分離セットアップ](user/speaker_diarization_setup.md)** - HuggingFaceトークン設定、pyannote.audio v3.3.2特化
2. **[tc CLI使用方法](developer/new_cli_usage.md)** - `./tc --enable-diarization`コマンド
3. **[トラブルシューティング](user/TROUBLESHOOTING.md)** - 話者分離エラー対処

### 🔧 開発者・上級者向け
1. **[API仕様書](developer/API.md)** - tc CLI対応プログラマー向けガイド
2. **[コーディング標準](developer/coding_standards.md)** - 統一システム（core/）規約
3. **[設定システム](user/configuration.md)** - config.yaml自動読み込み・統一設定

### 🐛 トラブルシューティング
1. **[トラブルシューティングガイド](user/TROUBLESHOOTING.md)** - tc CLIトラブルシューティング完全版
2. **[uv環境問題](../README.md#トラブルシューティング)** - 依存関係エラー対応
3. **[Google Drive認証問題](user/configuration.md)** - credentials.json/token.pickle設定

## 📅 最新情報・更新状況

### 2025年8月 プロダクション対応完了
- ✅ **tc CLIコマンド完成** - `./tc` でシンプル実行、config.yamlから自動設定読み込み
- ✅ **uv環境移行完了** - pip比較10倍高速インストール（170パッケージを30秒）
- ✅ **Google Drive完全自動化** - YouTube動画→転写→同一フォルダ自動アップロード
- ✅ **警告抑制完了** - transformers/googleapiclientの不要ログを完全抑制
- ✅ **docs構造化完了** - 43ファイルから26ファイルに整理、カテゴリ分類
- ✅ **プロダクション品質** - 完全動作確認済み、手動設定不要

### 📊 ドキュメント統計
- **有効ドキュメント数**: 26ファイル（archive/に17ファイル整理済み）
- **カテゴリ構造**: 5フォルダ分類で見やすく整理
  - **user/**: ユーザー向けガイド (5ファイル)
  - **developer/**: 開発者向けガイド (4ファイル)
  - **system/**: システムドキュメント (4ファイル)
  - **plans/**: 計画・設計 (6ファイル)
  - **reports/**: 分析・レポート (8ファイル)
  - **archive/**: 履歴・アーカイブ (17ファイル)
- **最終更新**: 2025年8月11日
- **対応言語**: 日本語・英語
- **技術レベル**: 初心者〜上級者、tc CLI中心の説明

## 🔍 ドキュメント検索ガイド

### 機能別検索
- **話者分離**: `user/speaker_diarization_setup.md`
- **多言語対応**: `user/language_support_guide.md`
- **パフォーマンス**: `system/optimization_features.md`
- **設定**: `user/configuration.md`
- **トラブル**: `user/TROUBLESHOOTING.md`

### フォルダ別アクセス
- **user/**: 今すぐ使いたい人向け
- **developer/**: カスタマイズしたい人向け
- **system/**: システム全体を理解したい人向け
- **plans/**: 将来の機能を知りたい人向け
- **reports/**: 開発状況を確認したい人向け
- **archive/**: 過去の経緯を調べたい人向け

## 📞 ドキュメントに関するフィードバック

### 改善要求・質問
- **GitHub Issues**: ドキュメント改善要求
- **内容追加**: 不足している情報の指摘
- **誤記訂正**: 誤字・脱字・技術的誤りの報告

### 貢献方法
1. **新規ドキュメント作成**: 新機能・用途別ガイド
2. **既存ドキュメント改善**: 内容更新・詳細追加
3. **翻訳作業**: 英語版ドキュメント作成

---

## 📝 クイック リファレンス

### 最も重要なドキュメント（上位5つ）
1. **[メインREADME](../README.md)** - tc CLI基本使用方法、uv環境セットアップ（必読）
2. **[初心者チュートリアル](user/TUTORIAL.md)** - ステップバイステップガイド
3. **[tc CLI使用方法](developer/new_cli_usage.md)** - プロダクションCLI詳細ガイド
4. **[トラブルシューティング](user/TROUBLESHOOTING.md)** - 全エラー対応ガイド
5. **[API仕様書](developer/API.md)** - プログラマー向けガイド

### 緊急時・問題解決
- 🚨 **tcコマンドエラー**: [トラブルシューティング](user/TROUBLESHOOTING.md)
- 🚨 **uv環境問題**: [メインREADME](../README.md#トラブルシューティング)
- 🚨 **YouTube/Google Driveエラー**: [トラブルシューティング](user/TROUBLESHOOTING.md)
- 🚨 **話者分離エラー**: [話者分離セットアップ](user/speaker_diarization_setup.md)

---

**最終更新**: 2025年8月11日  
**ドキュメントバージョン**: v2025.08 - tc CLI対応版  
**システム対応**: プロダクション対応完了  
**推奨環境**: uv + tc CLI  
**多言語**: 日本語・英語対応