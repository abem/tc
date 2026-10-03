# 多言語対応ガイド - モデル・言語設定

## 📋 概要

本システムは `config/config.yaml` の `whisper.model` で指定したモデルを使って文字起こしを行います。
モデル名のパターンによって内部エンジン（Nemotron系 / Qwen3-ASR系 / Whisper系）が自動的に切り替わり、
`whisper.language` の指定は各エンジンの言語指定へ変換されます。

## 🎯 対応言語とモデル

### デフォルト構成

- **デフォルトモデル**: `Qwen/Qwen3-ASR-1.7B`（`config.yaml` の `whisper.model`）
- **言語**: `whisper.language` の既定は `null`（自動判定）。`ja` / `en` を指定するとその言語を指定して認識する
- **特徴**: 日本語・英語とも同一モデルで対応するため、言語ごとにモデルを別々に指定する必要はない

### モデルを明示的に切り替える場合

`whisper.model` を書き換える（または `--model` で上書きする）ことで、別のエンジンへ切り替えられます。

| モデル | エンジン | 主な用途 | 出力形式 |
|--------|---------|----------|----------|
| `Qwen/Qwen3-ASR-1.7B` | Qwen3ASREngine | 日本語・英語（デフォルト） | テキスト（文節ごとに改行）。`include_timestamps` を有効にしたときだけ各行頭に `[MM:SS]` |
| `kotoba-tech/kotoba-whisper-v2.2` | WhisperTranscriptionEngine | 日本語特化（Whisperベース） | 設定に関係なく、常に 30 秒ごとの `[MM:SS]` 付き |
| `openai/whisper-large-v3` | WhisperTranscriptionEngine | 多言語対応の標準モデル | 設定に関係なく、常に 30 秒ごとの `[MM:SS]` 付き |
| `nvidia/nemotron-3.5-asr-streaming-0.6b` | NemotronSubprocessEngine | Nemotron（専用の仮想環境が必要。後述） | テキスト 1 本（タイムスタンプなし） |

`[MM:SS]` の付き方の詳細（入口ごとの違いを含む）は [タイムスタンプ機能](../feature/timestamp_feature.md) を参照してください。

### Nemotron を使う場合の前提

Nemotron は通常の `.venv` では動かせず、専用の仮想環境 `venv-nemotron/` のPythonをサブプロセスとして呼び出します
（`core/nemotron_engine.py`）。使う前に一度、次を実行して環境を作ります。

```bash
./scripts/setup_nemotron_venv.sh
```

`venv-nemotron/` が既に存在する場合、このスクリプトは何もせずに終了します（作り直す場合は先に `rm -rf venv-nemotron`）。
未構築のままNemotronを指定すると、このスクリプトの実行を促すエラーになります。

Nemotron では `whisper.context_file`（認識ヒント）と `whisper.include_timestamps`（タイムスタンプ付与）は使われません
（`core/nemotron_engine.py` がこれらを参照しないため）。

## 🔄 エンジン・言語の解決の仕組み

### 1. エンジン自動選択（モデル名ベース）

`core/engine_factory.py` の `create_engine`（`UnifiedTranscriber.__init__` から呼ばれる）が `whisper.model` の値だけを見て判定する:

```python
# core/engine_factory.py (create_engine)
if is_nemotron_model(config.model):
    return NemotronSubprocessEngine(config)
if Qwen3ASREngine.is_qwen3_model(config.model):
    return Qwen3ASREngine(config)
return WhisperTranscriptionEngine(config)
```

- `is_nemotron_model()` は、モデル名（小文字化）に `nemotron` を含むかどうかで判定する。
- `is_qwen3_model()` は、モデル名に `qwen3-asr` または `qwen3_asr` を含むかどうかで判定する。

**言語(`whisper.language`)は一切見ない** — エンジン選択は完全にモデル名依存。

> **注記**: 言語ごとにデフォルトモデルを選ぶ仕組み(旧 `select_model()`)は削除済みです。
> `config.yaml` に `whisper.language_models` を書いても実行パスには影響しません。

### 2. 言語の扱い(エンジンごとに異なる)

- **Qwen3ASREngine**: `ja` → `Japanese`、`en` → `English` に変換して Qwen3-ASR の `language` 引数として渡す
  （`core/qwen3_engine.py` の `lang_map = {"ja": "Japanese", "en": "English"}`）。
  それ以外の値と `null` は指定なし（自動判定）になる。モデル自体は切り替わらない。
- **WhisperTranscriptionEngine**: `whisper.language` の値をそのまま Whisper の `language` へ渡す。`./tc --language` は
  任意の文字列を受け付けるので、`ja` / `en` 以外もそのまま渡る（Whisper がその値を扱えるかは Whisper 側の仕様で、
  このリポジトリでは動作を確認していない）。`null` のときは `None` を渡す。
- **NemotronSubprocessEngine**: `ja` → `ja-JP`、`en` → `en-US` に変換して渡す。
  それ以外の値と `null` は `auto`（自動判定）になる（`core/nemotron_engine.py` の `_resolve_language`）。

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

`transcribe.py`（プロファイル版CLI）を使う場合は `--profile` でモデル・言語を選ぶ
（プロファイルの内容は [CLIの使用方法](new_cli_usage.md) を参照）。
こちらは `config.yaml` の `whisper.model` / `whisper.language` を読まない（プロファイル固定値かカスタム入力を使う）。

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

#### 英語音声が日本語として認識される
**原因**: `whisper.language` / `--language` に `ja` を指定している（指定すると強制されます）。
`./transcribe.py` のプロファイル 1・5 も `ja` で動きます
**解決法**: `--language en` を明示的に指定する（`./transcribe.py` ならプロファイル 3 か `--language en`）、
または `config.yaml` の `whisper.language` を `null`（自動判定）にする

#### 想定と違うモデルが使われる
**原因**: `config.yaml` の `whisper.model` が想定と異なる値になっている、または `--model` で上書きされている
**解決法**: 実行時ログの `文字起こし開始: モデル=...` 行で実際に使われたモデル名を確認する

### デバッグ方法
```bash
# ログを保存してモデル・言語の解決状況を確認
./tc path/to/audio.wav --language en --no-upload 2>&1 | tee debug.log

# 設定ファイル確認
uv run python3 -c "
import yaml
config = yaml.safe_load(open('config/config.yaml'))
print(config['whisper']['model'], config['whisper']['language'])
"
```

## 📞 サポート

### ログ確認
モデル・言語選択の問題がある場合、以下のログを確認:
```bash
# ログファイルを追う
tail -f logs/transcription.log | grep -E "(言語|モデル|文字起こし開始)"
```

### バグレポート
モデル・言語選択に関する問題は以下の情報を含めて報告:
- 使用したコマンド
- 期待されるモデル
- 実際に選択されたモデル（ログの「文字起こし開始: モデル=...」行）
- ログファイルの該当部分

---

**言語の指定**: 既定は自動判定（`whisper.language: null`）。`./tc --language` は任意の文字列、
`./transcribe.py --language` と WebUI は `ja` / `en`（WebUI は「自動判定」も選べる）。
エンジンごとの扱いは「言語の扱い」の節のとおりで、Qwen3-ASR と Nemotron は `ja` / `en` 以外の値を指定しても自動判定になります。
**デフォルトモデル**: Qwen/Qwen3-ASR-1.7B（言語共通・エンジン自動選択はモデル名ベース）
