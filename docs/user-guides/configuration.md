# 設定ガイド ⚙️

transcribe_audioシステムの設定管理に関するガイドです。
ここに載せている項目は、コードが実際に読み、動作に影響するものだけです。

## 📋 目次

- [設定ファイル概要](#設定ファイル概要)
- [config.yaml詳細](#configyaml詳細)
- [環境変数](#環境変数)
- [実行時パラメータ](#実行時パラメータ)
- [Python APIでの指定](#python-apiでの指定)
- [トラブルシューティング](#トラブルシューティング)

## 設定ファイル概要

設定は次の階層で管理します（後ろほど優先）：

1. **config/config.yaml** - メイン設定ファイル
2. **コマンドライン引数** - 実行時の上書き（`./tc` の `--model` / `--language` / `--device` 等）

`./tc` 以外のエントリポイントは `config/config.yaml` を相対パスで読むため、リポジトリのルートで実行してください。

どの項目をどの入口が読むかは次のとおりです。

| 項目 | `./tc` | `./transcribe.py` | WebUI（`webui.py`） |
|------|:------:|:-----------------:|:-------------------:|
| `gdrive.url`（入力省略時のURL） | 読む | 読む | 読まない |
| `gdrive.upload_folder_id` | 読む | 読む | 読まない |
| `whisper.model` / `whisper.language` / `whisper.device` | 読む | 読まない（プロファイルで指定） | 読まない（画面で指定） |
| `whisper.context_file` | 読む | 読む | 読まない（画面で指定） |
| `whisper.include_timestamps` | 読む | 読まない | 読まない（画面で指定） |

## config.yaml詳細

### 基本構造

```yaml
# config/config.yaml
gdrive:          # Google Drive連携設定
whisper:         # 音声認識設定（キー名は whisper だが、全エンジン共通の設定）
```

### Google Drive設定

```yaml
gdrive:
  url: "<デフォルトで処理する入力URL>"   # ./tc / ./transcribe.py の入力を省略したとき使う
  upload_folder_id: null                 # アップロード先フォルダID（省略時は元ファイルと同じフォルダ）
  # scopes: [...]                        # 省略可。OAuthスコープ（省略時は https://www.googleapis.com/auth/drive）
```

- **`url`**: YouTube / X / Google Drive の URL を書けます（入力と同じ判定）。
- **`upload_folder_id`**: Google Drive 入力の結果を保存するフォルダID。優先順位は
  `--folder-id` 引数 > `upload_folder_id` > 元ファイルと同じフォルダ。YouTube 入力のアップロード先は
  この設定の対象外です（`handlers/gdrive.py` の `upload_youtube_transcription` が決めるフォルダに保存されます）。
- **認証ファイル**: `credentials.json` と `token.pickle` は、実行したディレクトリ直下の固定名のファイルを使います
  （`config.py` の `get_drive_service`）。`config.yaml` でファイル名は変えられません。
  `token.pickle` が無い・無効な場合は、初回に認証URLが表示され、ブラウザで認証後に
  リダイレクト先の完全なURLを貼り付ける対話式の認証になります。

### 音声認識設定

```yaml
whisper:
  model: Qwen/Qwen3-ASR-1.7B             # 使用するモデル
  language: null                         # null=自動判定。ja / en 等を指定すると強制
  device: cuda                           # cuda / cpu / auto
  context_file: "config/context_hints.txt"  # 固有名詞・専門用語の認識ヒントファイル（下記参照）
  include_timestamps: false              # true で各行頭に [MM:SS] を付与（Qwen3-ASR専用）
```

- **`model`**: モデル名に応じて 3 つのエンジンから自動選択されます。

  | モデル名に含まれる文字列 | エンジン |
  |--------------------------|----------|
  | `nemotron` | NemotronSubprocessEngine（専用の仮想環境 `venv-nemotron/` が必要） |
  | `qwen3-asr` / `qwen3_asr` | Qwen3ASREngine（既定） |
  | 上記以外 | WhisperTranscriptionEngine |

  判定は `core/transcription_interface.py` の `UnifiedTranscriber.__init__` で行います。
  Nemotron の準備は `./scripts/setup_nemotron_venv.sh`（詳細は [多言語対応ガイド](language_support_guide.md)）。
- **`language`**: エンジンごとの扱いは [多言語対応ガイド](language_support_guide.md) を参照。
- **`device`**: `auto` は CUDA が使えれば `cuda`、使えなければ `cpu` になります。
- **`include_timestamps`**: `true` にすると ForcedAligner（`Qwen/Qwen3-ForcedAligner-0.6B`）を追加で読み込み、
  GPUメモリを約1.2GB追加で使います。Qwen3-ASR 以外のエンジンでは使われません。詳細は
  [timestamp_feature.md](../feature/timestamp_feature.md) を参照。

> `config.yaml` に上記以外のキーを書いても、現在のコードは読まないため結果は変わりません。

#### `context_file`（固有名詞・専門用語のヒント）

`Qwen3-ASR` 系モデルの使用時のみ有効です（WhisperTranscriptionEngine と NemotronSubprocessEngine は使いません）。
`./tc` または `./transcribe.py` の実行時に、人名・製品名・専門用語など誤変換しやすい語を専用ファイルで渡すことで、
認識精度を改善できます。

**使い方**:

```bash
# 1. サンプルをコピーして実ファイルを作成する
cp config/context_hints.txt.sample config/context_hints.txt

# 2. 誤変換されやすい語を1行に1つずつ記載する
```

`config/context_hints.txt` の書式:

```
# '#'で始まる行と空行はコメント・無視される
田中太郎
GAZOO Racing
スーパーGT
```

記載した語彙はすべて連結され、Qwen3-ASRへの認識ヒント文字列として渡されます。
`config/context_hints.txt` は `.gitignore`（`*.txt`）により既定でGit管理対象外です
（固有名詞・個人情報を誤ってコミットしないため）。`context_file` のパスは
`whisper.context_file` で変更できます。

ファイルが存在しない場合・内容が空（コメントのみ含む）の場合は、ヒントなしで動作します。

## 環境変数

このリポジトリのコードが独自に読む環境変数はありません。`./tc` は起動時に `.env`（`python-dotenv`）を読み込みますが、
その値を読むのは PyTorch や Hugging Face などの外部ライブラリです。たとえば次の標準の変数が使えます。

```bash
export CUDA_VISIBLE_DEVICES=0           # 使用するGPU ID（PyTorch/CUDA側の標準変数）
export HF_HOME=/custom/cache/path       # Hugging Faceのキャッシュ先（Hugging Face側の標準変数）
```

## 実行時パラメータ

### tc パラメータ

```bash
./tc audio.wav --language ja          # 言語を指定（省略時は config.yaml の値。既定は自動判定）
./tc audio.wav --device cuda          # cuda / cpu / auto
./tc audio.wav --model "openai/whisper-large-v3"   # モデルを上書き
./tc audio.wav --output-dir ./output  # 出力ディレクトリ（既定: output）
./tc audio.wav --no-upload            # Google Driveへアップロードしない
./tc --folder-id <フォルダID>          # Google Drive入力のアップロード先を指定
./tc audio.wav --dry-run              # 起動確認のみ（文字起こししない）
```

`./tc --help` で実際の一覧を確認できます。出力形式は常にテキスト（`<日時>_transcription.txt`）です。

### transcribe.py パラメータ

```bash
./transcribe.py audio.wav --profile 5   # プロファイル番号（1 / 3 / 5 / 6）
./transcribe.py audio.wav --language en # 言語（ja / en）
```

プロファイルの内容は [CLIの使用方法](new_cli_usage.md) を参照してください。

## Python APIでの指定

```python
from core.config import TranscriptionConfig
from core.transcription_interface import UnifiedTranscriber

# エンジンが読む項目: model / language / device / context / include_timestamps
config = TranscriptionConfig(
    model="Qwen/Qwen3-ASR-1.7B",
    language="ja",            # None で自動判定
    device="cuda",
    context="",               # 認識ヒント文字列（Qwen3-ASR専用）
    include_timestamps=False,
)

transcriber = UnifiedTranscriber(config)
result = transcriber.transcribe("audio.wav")
print(result.text)
```

`config.yaml` の値は `UnifiedConfig` で取得できます。

```python
from core.config import UnifiedConfig

UnifiedConfig.load("config/config.yaml")
model_name = UnifiedConfig.get("whisper", "model")
folder_id = UnifiedConfig.get("gdrive", "upload_folder_id", default=None)
```

## トラブルシューティング

### よくある設定問題

**Q: CUDA out of memory**
```bash
# CPUで実行する
./tc audio.wav --device cpu
```
長い音声は自動で分割して処理されます（分割の閾値は Qwen3-ASR が 300 秒、Nemotron が 350 秒で、設定では変えられません）。

**Q: モデルダウンロードエラー**
```bash
# Hugging Faceのキャッシュを削除して再取得（モデルを再ダウンロードします）
rm -rf ~/.cache/huggingface

# プロキシ設定
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
```

**Q: 設定ファイルが読み込まれない**
```bash
# 設定ファイルの場所と権限を確認（リポジトリのルートで実行する）
ls -la config/config.yaml

# YAML構文チェック (uv 経由)
uv run python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
```

### 設定デバッグ

```bash
# 現在の設定値を確認
uv run python -c "
from core.config import UnifiedConfig
UnifiedConfig.load('config/config.yaml')
print(UnifiedConfig.get('whisper'))
print(UnifiedConfig.get('gdrive'))
"
```

### 設定のバックアップ・復元

```bash
# 設定バックアップ
cp config/config.yaml config/config.yaml.backup.$(date +%Y%m%d)

# 設定を最後にコミットした状態へ戻す
git checkout config/config.yaml
```

---

## 📞 サポート

不具合や設定に関する質問は、リポジトリの Issue でお知らせください。
