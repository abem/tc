# 依存関係構造の移行ガイド

> **⚠️ 廃止済ドキュメント:** この文書は **uv 移行前** の古い移行記録です。
> 記載されている `requirements/base.txt` / `requirements/dev.txt` /
> `venv-clean` 等はすべて廃止され、現在は **uv** (pyproject.toml / uv.lock) が
> 唯一の依存関係情報源です。最新のセットアップ手順は
> `docs/user-guides/TUTORIAL.md` / `CONTRIBUTING.md` / `DEVELOPMENT.md` を
> 参照してください。以下は歴史記録として残しています。

## 概要
依存関係の管理を整理し、用途別に明確に分離した新しい構造に移行しました。

## 新しい構造

```
requirements/
├── base.txt          # 本番環境用コア依存関係
├── dev.txt           # 開発ツール（base.txt を含む）
├── monitoring.txt    # モニタリング機能（base.txt を含む）
├── ci.txt           # CI/CD最小構成
└── README.md        # 使用方法の説明
```

## 移行マッピング

| 旧ファイル | 新ファイル | 説明 |
|-----------|-----------|------|
| requirements.txt | requirements/base.txt | 固定バージョンから範囲指定に変更 |
| requirements-minimal.txt | requirements/base.txt | 内容を統合 |
| requirements-monitoring.txt | requirements/monitoring.txt | base.txt を継承する形に変更 |
| requirements-ci.txt | requirements/ci.txt | 最小構成を維持 |

## 主な改善点

1. **バージョン管理の統一**
   - セマンティックバージョニングによる範囲指定
   - メジャーバージョンの破壊的変更を防ぐ

2. **依存関係の階層化**
   - base.txt を基本として、他のファイルが継承
   - 重複の排除

3. **用途の明確化**
   - 本番、開発、モニタリング、CIで明確に分離
   - 必要最小限のパッケージのみインストール

## 移行手順

1. 既存の仮想環境をバックアップ
   ```bash
   cp -r venv-clean venv-clean.bak
   ```

2. 新しい依存関係でテスト
   ```bash
   # 新しい仮想環境で確認
   python -m venv venv-test
   source venv-test/bin/activate
   pip install -r requirements/dev.txt
   ```

3. 動作確認後、本番環境を更新
   ```bash
   source venv-clean/bin/activate
   pip install -r requirements/base.txt
   ```

## 注意事項

- 旧requirements*.txtファイルは互換性のため一時的に保持
- 全ての機能が正常動作することを確認後に削除予定
- CI/CDスクリプトの更新が必要な場合あり