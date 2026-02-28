# tcプロジェクト 現状調査・診断レポート

**調査日:** 2026年3月1日
**対象:** `<repo_root>` (Python音声文字起こしプロジェクト)

---

## 調査サマリー

音声文字起こしCLIツール。`core/`が統一システム、`handlers/`が外部サービス連携。ルート`config.py`は認証専用で`core/config.py`と役割分離済み。テスト41件、後方互換エイリアスあり。

---

## 事実

### エントリーポイント一覧

| ファイル | 種別 | 状態 | 用途 |
|---------|------|------|------|
| `tc` | CLIスクリプト | 活用中 | config.yaml対応の簡易CLI |
| `transcribe.py` | CLIスクリプト | 活用中 | Rich UI対話型CLI |
| `speaker_diarization.py` | スタンドアロン | 活用中 | 話者分離テスト・実行 |

### 主要モジュールの責務

| モジュール | 行数 | 責務 |
|-----------|------|------|
| `core/config.py` | 232 | TranscriptionConfig, DiarizationConfig, UnifiedConfig |
| `core/logging.py` | 205 | UnifiedLogger, PerformanceLogger |
| `core/transcription_interface.py` | 591 | UnifiedTranscriber, TranscriptionResult |
| `core/model_manager.py` | 347 | モデルキャッシュ管理 |
| `core/cli_common.py` | 73 | CLI共通ヘルパー |
| `core/cli_workflow.py` | 111 | 入力解決・アップロードフロー |
| `core/utils.py` | 73 | URL検出・デバイス解決 |
| `handlers/gdrive.py` | 430 | Google Drive操作（統合クライアント） |
| `handlers/youtube.py` | 215 | YouTube音声抽出 |
| `config.py` (ルート) | 107 | Google Drive認証（`get_drive_service`のみ） |

### 依存関係の中心（import集約点）

```
core/__init__.py (統一エクスポート)
    ├── core.config (TranscriptionConfig, UnifiedConfig)
    ├── core.logging (get_logger)
    ├── core.utils (URL検出関数)
    ├── core.model_manager (get_global_model_manager)
    └── core.transcription_interface (UnifiedTranscriber)

handlers/__init__.py
    ├── handlers.gdrive (GDriveClient)
    └── handlers.youtube (YouTubeClient)
```

### 外部I/F依存

- **Google Drive API**: `credentials.json`, `token.pickle`, `config.get_drive_service()`
  - ※これら認証ファイルは`.gitignore`でgit管理外
  - ※配布手順は未整備。`docs/credential_setup.md` として要整備（必要ファイル、配置場所、作成/更新手順、権限、再発行手順を記載）。
- **YouTube**: `yt-dlp` (外部コマンド)
- **HuggingFace**: pyannote.audio (話者分離)

---

## 根拠

### 参照一覧（モジュールごとの被参照）

#### `core.config`
- `core/__init__.py` - エクスポート
- `core/cli_common.py:11` - `UnifiedConfig`
- `core/transcription_interface.py:17` - `TranscriptionConfig, DiarizationConfig`
- `handlers/gdrive.py:21` - `UnifiedConfig`
- `speaker_diarization.py:26` - `TranscriptionConfig, DiarizationConfig`
- `transcribe.py:40` - `UnifiedConfig, TranscriptionConfig, DiarizationConfig`
- `tc:29` - `TranscriptionConfig`

#### `core.logging`
- `core/__init__.py` - エクスポート
- `core/model_manager.py:15` - `UnifiedLogger, PerformanceLogger`
- `core/transcription_interface.py:18` - `UnifiedLogger, PerformanceLogger`
- `config.py:13` - `get_logger`
- `handlers/gdrive.py:22` - `get_logger`
- `handlers/youtube.py:14` - `get_logger`
- `speaker_diarization.py:27` - `UnifiedLogger`
- `tc:30` - `get_logger`

#### `core.transcription_interface`
- `core/__init__.py` - エクスポート
- `speaker_diarization.py:28` - `UnifiedTranscriber`
- `transcribe.py:41` - `UnifiedTranscriber`
- `tc:31` - `UnifiedTranscriber`

#### `core.cli_common`
- `transcribe.py:34-38` - `build_output_file, detect_input_type, resolve_device`
- `tc:28` - `build_output_file, extract_gdrive_file_id, is_google_drive_url, resolve_device`

#### `core.cli_workflow`
- `transcribe.py:39` - `resolve_input_audio, upload_transcription_result`

#### `core.utils`
- `core/__init__.py` - エクスポート
- `core/cli_common.py:12-17` - `detect_input_type, extract_gdrive_file_id, is_google_drive_url, resolve_device`
- `handlers/youtube.py:15` - `is_youtube_url`

#### `handlers.gdrive`
- `handlers/__init__.py` - エクスポート
- `core/cli_common.py:59` - `GDriveClient`
- `core/cli_workflow.py:62,99` - `GDriveClient`
- `tc:32` - `GDriveClient`

#### `handlers.youtube`
- `handlers/__init__.py` - エクスポート
- `core/cli_workflow.py:43` - `YouTubeClient, check_yt_dlp_installed, install_yt_dlp`

#### `config.py` (ルート)
- `handlers/gdrive.py:20` - `get_drive_service`
- ※他モジュールからの直接参照なし

### 実行経路確認

| 経路 | 状態 |
|------|------|
| `tc` → `core.cli_common` → `handlers.gdrive` | OK |
| `tc` → `core.transcription_interface` → `core.model_manager` | OK |
| `transcribe.py` → `core.cli_workflow` → `handlers.*` | OK |
| `speaker_diarization.py` → `core.*` | OK |

### 役割分離の根拠（ルートconfig.pyとcore/config.py）

- `config.py`(ルート): `get_drive_service`関数のみ提供（認証処理）
- `core/config.py`: 認証処理は存在せず、設定データクラスのみ提供
- → 両者は責務が明確に分離されている

### テスト内訳（pytest件数）

| テストファイル | 対象 | テスト数 |
|--------------|------|---------|
| `test_core_config.py` | TranscriptionConfig, DiarizationConfig, UnifiedConfig | 7 |
| `test_core_logging.py` | UnifiedLogger, get_logger, PerformanceLogger | 6 |
| `test_core_utils.py` | URL検出、ファイルID抽出、デバイス解決 | 13 |
| `test_handlers_gdrive.py` | GDriveClient, エラークラス | 6 |
| `test_handlers_youtube.py` | YouTubeClient, yt-dlp確認 | 9 |
| `test_e2e_dry_run.py` | E2Eドライラン | 1 |
| **合計** | | **41** |

---

## リスク

### 高リスク

| 箇所 | 理由 | 影響範囲 |
|------|------|----------|
| `config.py` (ルート) | `handlers/gdrive.py`から直接import | 認証フロー変更でGDrive全停止 |
| `credentials.json` / `token.pickle` | 認証情報ファイル（`.gitignore`で管理外） | 紛失・破損で認証不可 |
| `core.transcription_interface.py` (591行) | 最大ファイル | 変更影響が全体に波及 |

### 中リスク

| 箇所 | 理由 | 影響範囲 |
|------|------|----------|
| `speaker_diarization.py` | 独自`SpeakerAwareTranscriber`を持つ | `UnifiedTranscriber`と二重実装 |
| 後方互換エイリアス | `handlers/gdrive.py:426-429`, `handlers/youtube.py:214`で定義 | 将来削除時の影響 |
| `core/__init__.py` | import時副作用あり（96-109行目: ロギング初期化・ログ出力） | import順序依存の可能性 |

注記: 後方互換エイリアスは現状各モジュール末尾に残存。将来は handlers/__init__.py への集約も検討余地あり。

### 低リスク

| 箇所 | 理由 | 影響範囲 |
|------|------|----------|
| `core/utils.py` | 純粋関数のみ | 変更容易 |
| `suppress_warnings.py` | 警告抑制のみ | 除去可能 |
| `setup_huggingface.py` | セットアップスクリプト | 実行時不要 |

---

## 提案

### 案1（最小変更）- 現状維持・小改善

**内容:**
- `config.py` (ルート) にdocstring追加で役割明確化
- 後方互換エイリアスに削除予定コメント追加
- テスト内訳維持

**メリット:** リスク最小、即時適用可能
**デメリット:** 技術的負債解消なし

### 案2（中）- 認証モジュールの統合

**内容:**
- `config.py` (ルート) → `core/auth.py` に移動
- `handlers/gdrive.py` のimportを `from core.auth import get_drive_service` に変更
- `speaker_diarization.py` の `SpeakerAwareTranscriber` を `UnifiedTranscriber` に統合
  - **前提条件:** 両者が同じ入出力契約であることを、統合前にコード上で確認する

**メリット:**
- `core/` 配下に統一完了
- 認証の責務が明確化
- 二重実装の解消

**デメリット:**
- importパス変更が必要
- テスト修正が必要

### 案3（大）- アーキテクチャ再編

**内容:**
- `core/transcription_interface.py` を分割（エンジン/インターフェース/結果クラス）
- CLIエントリーポイントを `cli/` ディレクトリに集約
- `config/` ディレクトリにYAML設定と認証を統合
- 依存性注入パターン導入

**メリット:**
- 保守性・テスタビリティ向上
- 拡張性確保

**デメリット:**
- 大規模変更
- 後方互換性の完全破棄

---

## 推奨案

**推奨: 案2（認証モジュール統合）**

### 採用条件

1. 次回リリースで破壊的変更を許容できる
2. テストが全て通る状態で実施
3. 段階的移行（エイリアス残存期間を設定）

### 理由

- `config.py` (ルート) が唯一の`core/`外依存
- 統合により`core/`が真に完結する
- `speaker_diarization.py`の二重実装も解消
- リスクが管理可能な範囲

### 実施手順

1. `core/auth.py` 作成（`config.py`の認証部分を移動）
2. `handlers/gdrive.py` のimport修正
3. ルート`config.py`に`from core.auth import *`でエイリアス追加
4. テスト実行・修正
5. `speaker_diarization.py` の `SpeakerAwareTranscriber` を deprecated 化

---

## 次に取るべきコマンド

```bash
# 参照一覧は rg による静的検索結果に基づく（実行時動的importは別途確認）
# 1. 現在のテスト状態確認
pytest -v

# 2. 認証部分の依存確認
rg "get_drive_service" -t py

# 3. speaker_diarization.pyの使用状況確認
rg "SpeakerAwareTranscriber" -t py

# 4. 未使用import確認
python -c "import core; print(dir(core))"

# 5. 行数推移確認（リファクタリング効果）
wc -l core/*.py handlers/*.py config.py

# 6. import graph生成（任意）
pip install pydeps && pydeps core --no-output -T png -o import_graph.png
```

---

*このレポートは takt system prompt 形式に従って生成されました。*
