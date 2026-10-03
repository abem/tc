# チュートリアル 🎥

音声文字起こしシステムの初心者向けステップバイステップガイドです。

## 📋 目次

- [事前準備](#事前準備)
- [基本的な使い方](#基本的な使い方)
- [YouTube・X動画の処理](#youtubex動画の処理)
- [Google Drive連携](#google-drive連携)
- [WebUIで使う](#webuiで使う)
- [設定のカスタマイズ](#設定のカスタマイズ)
- [トラブルシューティング](#トラブルシューティング)

## 🚀 事前準備

### ステップ1: システム要件確認

**必要な環境:**
```
✅ Python 3.12以上（pyproject.toml の requires-python）
✅ uv（依存関係の管理に使う）
✅ NVIDIA GPU（推奨。--device cpu でも指定できる）
```

GPU メモリの目安は、コード内に残された実測値だけが根拠です（RTX 4080 SUPER 16GB での値）。Qwen3-ASR（bf16）を
読み込んだ後で約 11.3GB、タイムスタンプ付与（ForcedAligner）を有効にすると約 12.5GB、Nemotron は 5 分の音声で
最大約 7.3GB です。それ以外の GPU、RAM、ストレージの最低要件と、CPU で処理したときの所要時間は**未確認**です
（モデルは初回に Hugging Face からダウンロードされます）。

YouTube / X の動画を処理するときは、yt-dlp が音声を wav に変換します。この変換には ffmpeg が使われるはずですが、
必須かどうかはこのリポジトリのコードでは**未確認**です。ffmpeg が入っているかは `which ffmpeg` で分かります。

**環境確認コマンド:**
```bash
# Python バージョン確認
python3 --version

# uv の確認
uv --version

# GPU確認（NVIDIA GPU使用時）
nvidia-smi
```

### ステップ2: リポジトリクローン

```bash
# GitHubからクローン
git clone <repository-url>
cd tc
```

### ステップ3: 仮想環境セットアップ

このプロジェクトは [uv](https://docs.astral.sh/uv/) で依存関係を管理しています。
pyproject.toml / uv.lock が情報源です。

```bash
# 依存関係インストール（.venv を自動作成）
# dev group(pytest 等)と Qwen3-ASR エンジンもデフォルトで含まれるため、素の uv sync で揃う
uv sync
```

### ステップ4: Nemotronを使う場合の準備（任意）

既定のモデル（Qwen3-ASR）と Whisper 系モデルは、ステップ3だけで使えます。
Nemotron（`nvidia/nemotron-3.5-asr-streaming-0.6b`）を使う場合だけ、専用の仮想環境 `venv-nemotron/` が必要です。

```bash
# Nemotron用の隔離環境を作る（既に venv-nemotron/ がある場合は何もしない）
./scripts/setup_nemotron_venv.sh
```

### ステップ5: 基本動作確認

```bash
# ヘルプ表示（動作確認）
./tc --help
```

**📸 期待される画面:**（先頭にログ行が 1 行付き、続けて使い方が表示されます）
```
2026-10-04 02:35:04,567 - core - INFO - Core unified modules initialized
usage: tc [-h] [--output-dir OUTPUT_DIR] [--no-upload] [--model MODEL]
          [--language LANGUAGE] [--device {cuda,cpu,auto}]
          [--folder-id FOLDER_ID] [--dry-run]
          [input]

音声文字起こしツール - YouTube URL・Google Drive URLまたはローカルファイルを文字起こし

positional arguments:
  input                 YouTube URL・Google Drive
                        URLまたはローカルファイルパス（省略時はconfig.yamlのURLを使用）

options:
  -h, --help            show this help message and exit
  --output-dir OUTPUT_DIR
                        出力ディレクトリ（デフォルト: output）
  --no-upload           Google Driveへのアップロードをスキップ
  --model MODEL         使用するモデル（config.yamlの設定を上書き）
  --language LANGUAGE   言語コード（config.yamlの設定を上書き）
  --device {cuda,cpu,auto}
                        使用するデバイス（config.yamlの設定を上書き）
  --folder-id FOLDER_ID
                        アップロード先Google DriveフォルダID（省略時は元ファイルと同じフォルダ）
  --dry-run             設定読み込み・入力解決までを行い、実際の文字起こしは行わずに終了する（起動確認用）
```

## 🎯 基本的な使い方

### シナリオ1: ローカル音声ファイルの文字起こし

**手順:**

1. **音声ファイルを準備**
```bash
# サンプル音声ファイルをプロジェクトディレクトリに配置
# 例: audio_sample.wav
ls -la *.wav
```

2. **基本的な文字起こし実行**
```bash
# 日本語音声の文字起こし（ローカルファイルは Google Drive にアップロードされない）
./tc audio_sample.wav --language ja
```

3. **実行中の画面表示**（表示内容の例。モデルの読み込みなどのログが間に入ることがあります）
```
2026-10-04 02:35:04,567 - core - INFO - Core unified modules initialized
2026-10-04 02:35:04,569 - __main__ - INFO - 設定ファイルを読み込みました
2026-10-04 02:35:04,570 - __main__ - INFO - 文字起こし開始: モデル=Qwen/Qwen3-ASR-1.7B, 言語=ja, デバイス=cuda
文字起こし完了: output/20261004_023512_transcription.txt

文字起こし結果（最初の500文字）:
こんにちは、今日は音声文字起こしのテストを行います。...
```
`日時 - ロガー名 - INFO - ` で始まる行がログで、`logs/transcription.log` にも同じ内容が記録されます。
`文字起こし完了:` と結果のプレビュー（500 文字を超えると `... (全N文字)` が付く）は、ログではなく画面への出力です。
300 秒を超える音声では、`文字起こし中 N/M チャンク完了` のような進捗も表示されます。
処理の記録は `output/history.db` にも追加されます（実行したディレクトリ基準のパスで、`--output-dir` を変えても
移りません。記録に失敗しても文字起こしは続行され、`変換履歴の記録に失敗しました: ...` と表示されます）。

4. **結果の確認**
```bash
# 出力ファイルの確認
ls -la output/
cat output/*_transcription.txt
```

**📸 期待される出力例:**
```
こんにちは、今日は音声文字起こしのテストを行います。この機能を使うことで、音声ファイルを自動的にテキストに変換できます。
```

既定モデル（Qwen3-ASR）と Nemotron は、既定ではテキストのみが出力されます。Qwen3-ASR で各行頭に `[MM:SS]` を付けたい
場合は、`config/config.yaml` の `whisper.include_timestamps` を `true` にします（[設定ガイド](configuration.md) を参照）。
Whisper 系のモデル（`--model kotoba-tech/kotoba-whisper-v2.2` など）は、この設定に関係なく、常に 30 秒ごとの
`[MM:SS]` が付きます。詳しくは [タイムスタンプ機能](../feature/timestamp_feature.md) を参照してください。

### シナリオ2: 英語音声の処理

```bash
# 英語音声の文字起こし
./tc english_audio.wav --language en --device cuda
```

**モデルの選択:**
- 既定は `Qwen/Qwen3-ASR-1.7B`（`config.yaml` の `whisper.model`）。日本語・英語とも同じモデルで処理する
- `--model` で上書きできる: `./tc english_audio.wav --language en --model openai/whisper-large-v3`
- 日本語: `--model kotoba-tech/kotoba-whisper-v2.2` なども指定できる（モデル名で Qwen3-ASR / Whisper /
  Nemotron のエンジンが自動で選ばれる。詳細は [多言語対応ガイド](language_support_guide.md)）

## 📺 YouTube・X動画の処理

### シナリオ3: 動画から音声抽出・文字起こし

**手順:**

1. **動画URLを準備**
```bash
# YouTube の例: https://www.youtube.com/watch?v=example123
# X(旧Twitter)の例: https://x.com/<ユーザー名>/status/<投稿ID>
```

2. **基本的な処理**
```bash
# YouTube動画の文字起こし
./tc "https://www.youtube.com/watch?v=example123" --language ja

# X(旧Twitter)の動画投稿
./tc "https://x.com/<ユーザー名>/status/<投稿ID>" --language ja
```

3. **実行中の画面表示**（表示内容の例。ログ行には `日時 - ロガー名 - INFO - ` が付きます）
```
YouTube URLを検出
ダウンロード中 10%(残り 00:12)
...（10% ごとに進捗が出て、yt-dlp 自身のダウンロード進捗行も表示されます）
音声をwavに変換中(長い動画は数分かかります)
2026-10-04 02:35:40,100 - __main__ - INFO - 文字起こし開始: モデル=Qwen/Qwen3-ASR-1.7B, 言語=ja, デバイス=cuda
文字起こし完了: output/20261004_023612_transcription.txt
アップロード完了: https://drive.google.com/file/d/<結果ファイルID>/view
```
X の URL では「X(Twitter)動画URLを検出」と表示され、アップロードはありません。

4. **処理完了確認**
```bash
# 文字起こし結果
ls -la output/
```
ダウンロードした音声（`<タイトル>_<動画ID>.wav`）は `--output-dir`（既定は `output/`）に一時保存され、
処理の終了時（成功・失敗・中断のいずれでも）に削除されます。削除に失敗したときは警告だけが表示されます。
ローカルファイルを入力したときは、元のファイルは削除されません。

**yt-dlp まわりのエラー:**
- `yt-dlp が見つかりません。…`: yt-dlp が無いときのエラーです。自動インストールはしません。プロジェクトの
  ディレクトリで `uv sync` を実行してください（`./tc` は終了コード 1 で止まります）。
- yt-dlp の呼び出しにはタイムアウトがあります。メタデータ取得は 60 秒（ログに `Timed out getting video info (60s)`、
  続けて `Failed to get video info` で止まる）、ダウンロード中に yt-dlp の出力が 300 秒途絶えると
  `yt-dlp出力が300秒間停止したため中断` で止まります。詳細は [TROUBLESHOOTING.md](TROUBLESHOOTING.md) を参照してください。

YouTube 動画は、処理後に Google Drive へ自動アップロードされます（`--no-upload` で止められます）。
X の動画はアップロードされず、ローカルにのみ保存されます。

## ☁️ Google Drive連携

### シナリオ4: Google Drive上の音声ファイル処理

**事前準備:**

1. **Google Drive API認証設定**
```bash
# 実行するディレクトリ直下に credentials.json があることを確認
ls -la credentials.json
```
初回は認証URLが表示されます。ブラウザで認証したあと、リダイレクト先の完全なURLを貼り付けると、
`token.pickle` が作成されます（以降は自動で再利用）。

2. **設定ファイルでDrive URLを指定**
```yaml
# config/config.yaml
gdrive:
  url: "https://drive.google.com/file/d/your_file_id/view"
  upload_folder_id: null   # 結果の保存先フォルダID（null なら元ファイルと同じフォルダ）
```

**手順:**

1. **設定ファイル使用の基本実行**
```bash
# config.yamlで設定されたURLを使用
./tc
```

2. **コマンドラインでDrive URL指定**
```bash
# 直接Drive URLを指定
./tc "https://drive.google.com/file/d/1ABC123XYZ/view" --language ja
```

3. **実行中の画面表示**（表示内容の例）
```
Google Drive URLを検出、ダウンロードを開始
2026-10-04 02:35:10,100 - __main__ - INFO - 文字起こし開始: モデル=Qwen/Qwen3-ASR-1.7B, 言語=ja, デバイス=cuda
文字起こし完了: output/20261004_023512_transcription.txt
アップロード完了: https://drive.google.com/file/d/<結果ファイルID>/view
```
ダウンロードした音声は一時ファイルで、処理の終了時に削除されます（削除に失敗したときは警告だけ）。

4. **結果の確認**
```bash
# ローカル結果確認
cat output/*_transcription.txt
```
アップロード先は `--folder-id` > `gdrive.upload_folder_id` > 元ファイルと同じフォルダ、の優先順位で決まります。

## 🖥️ WebUIで使う

コマンドラインの代わりに、ブラウザから操作できる WebUI（`webui.py`、Streamlit 製）もあります。
本番環境では systemd のサービス `tc-webui.service` が常駐させているので、通常は起動の操作は要りません
（常駐化と内部構成は [WebUI内部サーバー構成](../system-docs/webui_architecture.md) を参照）。
手元で起動する場合は次のコマンドを使います。

```bash
uv run streamlit run webui.py --server.headless true --server.port 8501
```

起動後、ブラウザで `http://localhost:8501` を開きます。

### 文字起こしタブ

1. 「YouTube / Google Drive URL」欄に URL を入力するか（ラベルは YouTube / Google Drive ですが X の動画URLも
   入力できます）、「またはローカルファイルをアップロード」でファイルを選びます。
2. 「設定」で、モデル・デバイス・言語（既定は「自動判定」）を選びます。
   「タイムスタンプ付与」にチェックを入れると、保存テキストの各行頭に `[MM:SS]` が付きます（ForcedAligner を
   追加で読み込みます。Nemotron では選べません）。
3. 認識ヒント（固有名詞・専門用語）は、「認識ヒント」の折りたたみ欄に 1 行 1 語で入力し、リスク
   （入力した語が発話されていない区間に混入することがある）を理解したことを示すチェックを入れたときだけ使われます。
   チェックが無いときはヒントなしで処理されます。
4. 「キューに追加」を押します。複数の入力は順番に処理されます。

処理中は進捗バーと「経過 m:ss / 残り約 m:ss」が表示されます。進捗率が分かるのは、YouTube / X のダウンロード、
Qwen3-ASR で 300 秒を超える音声、Whisper 系です。残り時間は進捗が 3% に達してから出ます。Nemotron、300 秒以下の
Qwen3-ASR、Google Drive のダウンロードは、経過時間だけが表示されます。

完了すると、完了済み一覧に結果のテキストが出ます。結果は `output/<日時>_transcription.txt` に保存され、入力が
Google Drive / YouTube ならアップロードされます。アップロード先は、Google Drive 入力では常に元ファイルと同じ
フォルダです（WebUI は `config.yaml` の `gdrive.upload_folder_id` を読みません）。タイムスタンプ付与にチェックを
入れたときは「SRTプレビュー」も出ますが、区間の情報が無い場合は「SRTを生成できるタイムスタンプ情報がありません」と
表示されます。失敗した項目は `[失敗]` として完了済み一覧に残り、画面にエラーの文が出ます。
Google Drive 入力の音声は、処理後に削除されます（削除に失敗したときは警告が出ます）。

**アップロードの保存先と自動削除:**
- アップロードしたファイルは `output/uploads/<一意>/<ファイル名>` に保存され、同じ名前でも上書きされません。
  7 日を過ぎたものは、新しい入力を追加するたびに削除されます（処理待ち・処理中のファイルは消えません）。
  履歴に残るアップロード元のパスは、7 日後には存在しなくなります。
- URL 入力の作業領域 `output/queue_downloads/<トークン>/` は、1 日を過ぎたものが同じタイミングで削除されます。

ディスクの空きが減ってきたら、`output/uploads/` を確認してください（最大 7 日分が残ります）。

### 履歴タブ

- 過去の文字起こし（`output/history.db`）を、開始日・終了日と、キーワードで絞り込めます。
  **キーワードは 3 文字以上**で入力してください（2 文字以下では結果が得られません）。
- 各履歴の「出力対象に含める」にチェックを入れると、「選択履歴をまとめ出力」で、選んだ結果を 1 つの Markdown
  ファイルとしてダウンロードできます。
- 「古い履歴の一括削除」は、N 日より前の履歴を「① 対象件数を確認」→「② N 件を削除する」の 2 段階で消します。
  消えるのはデータベースの記録だけで、`output/` のテキストと Google Drive 上のファイルは消えません。

## ⚙️ 設定のカスタマイズ

### シナリオ5: 設定ファイルのカスタマイズ

**設定ファイルの編集:**

```bash
# 設定ファイルを開く
nano config/config.yaml
```

**主要設定項目:**

```yaml
# config/config.yaml
whisper:
  model: Qwen/Qwen3-ASR-1.7B     # モデル名（名前でエンジンが自動選択される）
  language: null                 # null=自動判定。ja / en を指定すると強制
  device: cuda                   # cuda / cpu / auto
  context_file: "config/context_hints.txt"  # 固有名詞のヒント（Qwen3-ASR専用）
  include_timestamps: false      # true で Qwen3-ASR の各行頭に [MM:SS] を付与（Whisper系は設定に関係なく常に付く）

gdrive:
  url: "your_default_url"        # 入力を省略したときに処理するURL
  upload_folder_id: null         # Google Drive入力の結果のアップロード先フォルダID
```

各項目の詳細は [設定ガイド](configuration.md) を参照してください。

**設定確認:**
```bash
# 設定値の確認 (uv 経由)
uv run python3 -c "from core.config import UnifiedConfig; UnifiedConfig.load(); print(UnifiedConfig.get('whisper'))"
```

### カスタム設定での実行例

```bash
# CPUを強制使用
./tc --device cpu "audio.wav"

# 実行ログをファイルにも保存
./tc "audio.wav" 2>&1 | tee debug.log

# GPU監視(別ターミナルで scripts/gpu_monitor.py を並行実行)
uv run python3 scripts/gpu_monitor.py &
./tc "audio.wav"
```

## 🔧 よく使う操作パターン

### パターン1: バッチ処理

```bash
# 複数ファイルの一括処理
for file in audio_files/*.wav; do
    echo "処理中: $file"
    ./tc "$file" --language ja --no-upload
done
```

### パターン2: モデルを切り替える

```bash
# Whisper系モデルで処理
./tc "audio.wav" --model openai/whisper-large-v3 --language ja
```

### パターン3: GPUが使えない環境で処理する

```bash
# CPUで処理（GPUより時間がかかる）
./tc --device cpu --language ja "audio.wav"
```

## 📊 結果の活用

### 出力ファイル形式

**基本テキスト形式（Qwen3-ASR・Nemotron の既定）:** 文字起こし結果のテキストのみ。

**タイムスタンプ付き形式:** Qwen3-ASR で `whisper.include_timestamps: true`（`./tc`）、または WebUI の
「タイムスタンプ付与」にチェックを入れると、各行頭に `[MM:SS]` が付きます。Whisper 系は設定に関係なく、
常に 30 秒ごとに付きます。`transcribe.py` は Qwen3-ASR で付きません。詳細は
[タイムスタンプ機能](../feature/timestamp_feature.md)。
```
[MM:SS] 文字起こしテキスト
[MM:SS] 続きのテキスト
```

### 後処理の例

```bash
# 最新の出力ファイルを変数に入れる
latest=$(ls -t output/*_transcription.txt | head -1)

# 文字数カウント
wc -c "$latest"

# 特定キーワード検索
grep -i "重要" "$latest"
```

## 🚨 トラブルシューティング

### よくある問題と解決法

**問題1: GPU out of memory**
```bash
# エラーメッセージ例
CUDA out of memory. Tried to allocate 2.00 GiB

# 解決策: CPUに切り替え
./tc --device cpu "audio.wav"
```

**問題2: Nemotron隔離venvが未構築**
```bash
# エラーメッセージ例
Nemotron隔離venvが未構築です。scripts/setup_nemotron_venv.sh を実行してから再度お試しください。

# 解決策: 隔離環境を作る
./scripts/setup_nemotron_venv.sh
```

**問題3: 音声ファイルが認識されない**
```bash
# エラーメッセージ例
入力を認識できません: audio.wav

# 解決策: パスと拡張子を確認（存在しないパスは「認識できません」になる）
ls -la audio.wav
file audio.wav
# 必要に応じて変換
ffmpeg -i audio.mp3 audio.wav
```

**問題4: YouTube / X のURLが処理できない**
```bash
# エラーメッセージ例
Failed to get video info
Audio extraction failed: ...
yt-dlp が見つかりません。プロジェクトのディレクトリで `uv sync` を実行して…
yt-dlp出力が300秒間停止したため中断: <URL>

# 解決策: URLの確認
echo "https://www.youtube.com/watch?v=VIDEO_ID"
# プライベート動画でないことを確認
# yt-dlp が無いと言われたら uv sync を実行する（自動インストールはされない）
```
タイムアウトの意味と対処は [TROUBLESHOOTING.md](TROUBLESHOOTING.md) にあります。

### デバッグ方法

```bash
# 実行ログをファイルに保存
./tc "audio.wav" 2>&1 | tee debug.log

# ログファイル確認
tail -f logs/transcription.log

# システム状態確認
nvidia-smi  # GPU使用状況
top         # CPU/メモリ使用状況
```

## 🎯 実践的な使用例

### 例1: 会議録音の処理

```bash
# 1時間の会議録音。ローカルファイルはアップロードされず output/ に保存される
./tc meeting_2026-10-02.wav --language ja
```

### 例2: 講演動画の処理

```bash
# YouTubeの講演動画(GPU使用状況を見たい場合は別ターミナルで
# uv run python3 scripts/gpu_monitor.py を並行実行する)
./tc "https://youtube.com/watch?v=lecture123" \
    --language ja \
    --device cuda
```

### 例3: 英語プレゼンテーションの処理

```bash
# 英語のプレゼンテーション音声
./tc presentation_en.wav \
    --language en \
    --device cuda
```

---

## 🎉 チュートリアル完了

おめでとうございます！これで音声文字起こしシステムの基本的な使い方をマスターしました。

### 次のステップ

- **[API仕様書](../developer-guides/API.md)** - プログラマー向け詳細情報
- **[開発者ガイド](../../DEVELOPMENT.md)** - カスタマイズ方法
- **[トラブルシューティング](TROUBLESHOOTING.md)** - 詳細な問題解決

高品質な音声文字起こしをお楽しみください！ 🎙️✨
