# 多言語対応ガイド - モデル・言語設定

## 📋 概要

本システムは `config/config.yaml` の `whisper.model` で指定したモデルを使って文字起こしを行います。
モデル名のパターンによって内部エンジン（Qwen3-ASR系 / Whisper系）が自動的に切り替わり、
`whisper.language` の指定は各エンジンの言語指定へ変換されます。

## 🎯 対応言語とモデル

### デフォルト構成

- **デフォルトモデル**: `Qwen/Qwen3-ASR-1.7B`（`config.yaml` の `whisper.model`）
- **対応言語**: 日本語(`ja`)・英語(`en`)。`whisper.language` で切り替える
- **特徴**: 2026年ベンチマークで最上位の精度。日本語・英語とも同一モデルで高精度に対応するため、
  言語ごとにモデルを別々に指定する必要はない

### モデルを明示的に切り替える場合

`whisper.model` を書き換える（または `--model` で上書きする）ことで、Whisper系エンジンへ切り替えられます。

| モデル | エンジン | 主な用途 |
|--------|---------|----------|
| `Qwen/Qwen3-ASR-1.7B` | Qwen3ASREngine | 日本語・英語とも最高精度（デフォルト） |
| `kotoba-tech/kotoba-whisper-v2.2` | WhisperTranscriptionEngine | 日本語特化（Whisperベース） |
| `openai/whisper-large-v3` | WhisperTranscriptionEngine | 多言語対応の標準モデル |

## 🔄 エンジン・言語の解決の仕組み

### 1. エンジン自動選択（モデル名ベース）

`core/transcription_interface.py` の `UnifiedTranscriber.__init__` が `whisper.model` の値だけを見て判定する:

```python
# core/transcription_interface.py (UnifiedTranscriber.__init__)
if Qwen3ASREngine.is_qwen3_model(transcription_config.model):
    self.transcription_engine = Qwen3ASREngine(transcription_config)
else:
    self.transcription_engine = WhisperTranscriptionEngine(transcription_config)
```

`is_qwen3_model()` はモデル名に `qwen3-asr` または `qwen3_asr` を含むかどうかで判定する。
**言語(`whisper.language`)は一切見ない** — エンジン選択は完全にモデル名依存。

> **注記**: `core/cli_common.py` の `select_model()` は「言語ごとにデフォルトモデルを選ぶ」関数だが、
> 現在どこからも呼ばれていない dead code（`config.yaml` の `whisper.language_models` コメント参照）。
> `language_models` セクションの値は現状の実行パスには影響しない。

### 2. 言語の扱い(エンジンごとに異なる)

- **Qwen3ASREngine**: `whisper.language` の値(`ja`/`en`)を `core/transcription_interface.py` の
  `lang_map = {"ja": "Japanese", "en": "English"}` で変換し、Qwen3-ASRモデルの `language` 引数
  （認識対象言語のヒント）として渡す。モデル自体は切り替わらない。
- **WhisperTranscriptionEngine**: `whisper.language` の値をそのまま(`ja`/`en`)Whisperへ渡す
  （変換不要。Whisperは同じ言語コード体系を使う）。

## 🚀 使用方法

### 基本的な使用例

```bash
# config.yamlの設定で自動実行(gdrive.url / whisper.model / whisper.language を使用)
./tc

# YouTube・X(Twitter)・Google Drive のURLを指定
./tc "https://www.youtube.com/watch?v=xxxx"

# ローカルファイルを直接指定
./tc path/to/audio.wav

# アップロードをスキップ
./tc path/to/audio.wav --no-upload
```

### 言語・モデルの上書き

```bash
# 言語を上書き(config.yamlの設定より優先)
./tc path/to/audio.wav --language en

# モデルを上書き(Whisperエンジンへ切り替える例)
./tc path/to/audio.wav --model "kotoba-tech/kotoba-whisper-v2.2" --language ja
./tc path/to/audio.wav --model "openai/whisper-large-v3" --language en
```

`transcribe.py`（インタラクティブ版CLI）を使う場合はプロファイル選択(`--profile`)または
カスタム設定でモデル・言語を選べる。ただしこちらは `config.yaml` の `whisper.model` 等を
自動では読まない(プロファイル固定値かカスタム入力を使う)。

## 📊 パフォーマンス比較

### 日本語音声での性能比較
| モデル | 文字起こし精度 | 処理速度 | 推奨用途 |
|--------|---------------|----------|----------|
| Qwen/Qwen3-ASR-1.7B | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 日本語音声（推奨・デフォルト）|
| kotoba-tech/kotoba-whisper-v2.2 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 日本語音声（Whisperエンジン）|
| openai/whisper-large-v3 | ⭐⭐⭐ | ⭐⭐⭐⭐ | 多言語対応 |

### 英語音声での性能比較
| モデル | 文字起こし精度 | 処理速度 | 推奨用途 |
|--------|---------------|----------|----------|
| Qwen/Qwen3-ASR-1.7B | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 英語音声（推奨・デフォルト）|
| openai/whisper-large-v3 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 英語音声（Whisperエンジン）|

## 🧪 テスト・検証

### 自動テストスイート
```bash
# pytest でコア設定/ユーティリティの単体テストを実行
uv run pytest -q
```

### 手動検証例

```bash
# デフォルト(Qwen3-ASR)でモデル名がログに出ることを確認
./tc path/to/audio.wav --no-upload 2>&1 | grep "Qwen/Qwen3-ASR-1.7B"

# Whisperエンジンへ切り替えた場合のモデル名を確認
./tc path/to/audio.wav --model "kotoba-tech/kotoba-whisper-v2.2" --language ja --no-upload 2>&1 \
  | grep "kotoba-tech/kotoba-whisper-v2.2"
```

## 🐛 トラブルシューティング

### よくある問題と解決法

#### 1. 英語音声が日本語として認識される
**原因**: `whisper.language` / `--language` が正しく渡されていない
**解決法**: `--language en` を明示的に指定するか `config.yaml` の `whisper.language` を確認する

#### 2. 想定と違うモデルが使われる
**原因**: `config.yaml` の `whisper.model` が想定と異なる値になっている、または `--model` で上書きされている
**解決法**: 実行時ログの `文字起こし開始: モデル=...` 行で実際に使われたモデル名を確認する

### デバッグ方法
```bash
# 詳細ログでモデル・言語の解決状況を確認
./tc path/to/audio.wav --language en --no-upload 2>&1 | tee debug.log

# 設定ファイル確認
uv run python3 -c "
import yaml
config = yaml.safe_load(open('config/config.yaml'))
print(config['whisper']['model'], config['whisper']['language'])
"
```

## 🔄 今後の拡張予定

### 追加予定言語
- **中国語**: `openai/whisper-large-v3` + 中国語特化モデル
- **韓国語**: 韓国語特化Whisperモデル
- **スペイン語**: スペイン語圏向け最適化

### 機能拡張
- 自動言語検出機能
- 混合言語音声への対応
- リアルタイム言語切り替え

## 📞 サポート

### ログ確認
モデル・言語選択の問題がある場合、以下のログを確認:
```bash
# 最新のログファイル確認
tail -f logs/transcribe.log | grep -E "(言語|モデル|文字起こし開始)"
```

### バグレポート
モデル・言語選択に関する問題は以下の情報を含めて報告:
- 使用したコマンド
- 期待されるモデル
- 実際に選択されたモデル（ログの「文字起こし開始: モデル=...」行）
- ログファイルの該当部分

---

**最終更新**: 2026年8月2日
**対応言語**: 日本語、英語
**デフォルトモデル**: Qwen/Qwen3-ASR-1.7B（言語共通・エンジン自動選択はモデル名ベース）
**話者分離**: 全言語対応
