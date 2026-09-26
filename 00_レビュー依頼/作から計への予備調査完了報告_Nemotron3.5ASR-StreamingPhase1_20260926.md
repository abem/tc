# 作から計への予備調査完了報告: Nemotron3.5ASR-StreamingPhase1

**報告日**: 2026-09-26
**報告者**: 作成ロール（作、saku）
**対象**: tc-ops #546 Nemotron-3.5-ASR-Streaming Phase1予備調査
**ブランチ**: feature/nemotron35-asr-phase1-investigation-20260926

## 実施概要

作業指示書（計から作への作業指示書_Nemotron3.5ASR-StreamingPhase1予備調査_20260926.md、査読合格sa、commit 1b12e49）に基づき、以下5項目を一次資料ベースで調査した。実際のモデルダウンロード・推論実行・依存関係の実インストールは行っていない。`.venv/`・`pyproject.toml`・`uv.lock`への変更なし（本報告書末尾の機械検査で確認）。

## 1. transformers衝突可否

### 結論

Transformers経路を選ぶ場合、現行生産用`.venv`（transformers==4.57.6固定、qwen-asr要求`<5`）と**衝突する**。NeMo経路はバージョン制約の直接衝突は原理的に回避できるが、依存解決自体に別の不確実性がある。いずれの経路でも、Phase1実測は現行`.venv`とは別の隔離環境で行う必要がある（→§2）。

### 実測・一次資料

- **Transformers要件**: HuggingFace公式モデルカード（`https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b`）に "Nemotron3_5Asr is available in 🤗 Transformers starting from v5.13.0." と明記。transformers公式ドキュメント（`https://huggingface.co/docs/transformers/main/en/model_doc/nemotron3_5_asr`）にも `Nemotron3_5AsrForRNNT` / `Nemotron3_5AsrProcessor` の実装が存在することを確認した。
- **現行.venv実測**（計提供値を本作でも再確認）: `uv.lock` L3002-3019は`transformers-4.57.6`。`pyproject.toml` L19は`"transformers>=4.56.1"`、L37-41のコメントに「qwen-asr は transformers<5 を要求する」旨。→ `transformers>=5.13.0`とは**直接衝突**（4.57.6 < 5.13.0であり、qwen-asr制約`<5`が上限を課しているため同一.venv内での両立は不可能）。
- **NeMo経路**: モデルカードに `pip install git+https://github.com/NVIDIA/NeMo.git@main#egg=nemo_toolkit[asr]` の記載あり。NeMo経路はtransformers>=5.13.0を直接要求しないため、原理上は現行.venvのtransformers<5制約と衝突しない可能性がある。ただし以下の別リスクを確認した:
  - PyPI実測（`https://pypi.org/project/nemo-toolkit/`）: 最新版は**nemo-toolkit 3.0.0**（2026-08-07リリース）。要件「Python 3.12以上」「PyTorch 2.7以上」が明記。現行.venv（Python 3.12.12・torch 2.11.0+cu130、実測）はこの要件自体は満たす。
  - 一方、`nemo_toolkit[asr]>=2.3.0`のように上限を指定せず解決させた実例（`https://github.com/talberthoule/backchannel/pull/36`、別プロジェクトの一次資料）では、「無制約指定が3.0.0に解決され、依存関係が周辺パッケージと解決できず、pipがtransformersを4.12.2(2021年)まで巻き戻し、tokenizers 0.10.3のソースビルドにRustコンパイラが必要になりビルドが失敗した」との記録がある。本プロジェクトへの直接適用ではないが、**nemo_toolkitの依存解決は上限指定なしでは予測困難**という一次資料上の傍証として扱う。
  - 加えて `https://github.com/NVIDIA-NeMo/NeMo/issues/14505`（NeMo公式issue、タイトル「Dependency conflict: (2.5.0rc0): nemo-toolkit[asr] incompatible with numpy>=2.0」）がnumpy側の既知の非互換issueとしてタイトル上確認できた（本文詳細は本調査では未取得。タイトルのみ一次資料として確認）。
- **結論の裏付け**: いずれの経路でも「現行.venvへ追加インストールする」設計は採用できない。NeMo経路は理論上transformers<5制約を回避できるが、依存解決自体に不確実性があるため、両経路とも隔離環境での検証が前提となる。

## 2. 隔離実行案

### 設計方針

生産用`.venv/`を一切変更せず、`uv venv`で別ディレクトリに独立した検証環境を作成する。`.gitignore` L62の`venv*/`パターンが命名`venv*`に既にマッチするため（実測: L62=`venv*/`、L65=`.venv/`）、規約に沿った命名（例: `venv-nemotron-poc/`）を使えば追加のgitignore変更も不要である。

### 手順案（コマンド例、Phase1実測時に使用）

```bash
# 1. 隔離venv作成(現行.venv/pyproject.toml/uv.lockには一切触れない)
cd /home/abem/Projects/tc
uv venv venv-nemotron-poc --python 3.12

# 2a. Transformers経路の検証環境
uv pip install --python venv-nemotron-poc/bin/python \
  "transformers>=5.13.0" torch --index-url https://download.pytorch.org/whl/cu130

# 2b. NeMo経路の検証環境(§1のbacktrack事例を踏まえ上限指定を必須とする)
uv venv venv-nemotron-poc-nemo --python 3.12
uv pip install --python venv-nemotron-poc-nemo/bin/python \
  "nemo_toolkit[asr]>=2.3.0,<3"

# 3. 動作確認(生産コードは一切importしない。単体スクリプトで完結させる)
venv-nemotron-poc/bin/python -c "from transformers import pipeline; print('import OK')"
```

### 現行コードとの整合性確認

`core/transcription_interface.py`の`TranscriptionEngine`（抽象基底、L73-121）は`transcribe()`/`get_engine_name()`の2メソッドを要求する構成。`Qwen3ASREngine`（L400-）・`WhisperTranscriptionEngine`（L122-）と同型の第3エンジンとして将来組み込む設計と整合させることは可能だが、**本予備調査では実装しない**（作業指示書§5でスコープ外と明記）。隔離venv内のPoCスクリプトは生産コード（`core/`配下）をimportしない単体スクリプトとして設計し、生産用.venvの依存解決に一切影響を与えない。

### リスクと対策

- ディスク容量: 実測`df -h /`で720GB空き（使用236GB/1007GB、`/dev/sdd`）。隔離venv＋モデル重み（600Mパラメータ、概算1.2〜2.4GB程度）で問題なし。
- GPU: §3参照。
- 隔離venvは検証後に`rm -rf venv-nemotron-poc*`で削除可能（gitignore対象のため誤コミットのリスクなし）。

## 3. VRAM要件

### 結論

モデルカード・公式ドキュメントに**VRAM要件の明示値はない**。パラメータ数600Mからの推定値と、実機の空きVRAMの実測を報告する。

### 一次資料

- HuggingFaceモデルカード・transformers公式ドキュメントのいずれにも、VRAM/GPUメモリに関する具体的な数値記載は確認できなかった（明示値なし）。
- パラメータ数: 600M（モデルカードに明記）。dtype未指定時の推定（一次資料に基づかない作の推定であることを明記）: float32なら概算2.4GB、float16/bfloat16なら概算1.2GB（重みのみ。KVキャッシュ・アクティベーション・CUDAコンテキスト等のオーバーヘッドは含まない）。

### 実機環境の実測（重要）

- GPU: NVIDIA GeForce RTX 4080 SUPER（実測: `nvidia-smi`）、VRAM総量16376MiB。
- **実測時点の空きVRAM: 2825MiB**（使用中13221MiB）。`nvidia-smi --query-compute-apps`では実行中プロセスが検出されなかった（空欄）が、使用量実測は13221MiBを示しており、原因は本調査では未特定（WSL2環境特有の表示制約の可能性はあるが未検証。事実のみ報告）。
- 600Mパラメータモデルの推定所要VRAM（重み1.2〜2.4GB＋推論時オーバーヘッド）は、**現在の空き2825MiBでは逼迫する可能性がある**。Phase1実測着手前に空きVRAMの再実測と、必要に応じた確保策をPhase1実行計画に含めるべきである（→§5）。

## 4. テスト音声選定

### 方針

本番Google Driveフォルダおよび`output/`配下（`output/queue_downloads/`等、本番パイプライン実行由来の可能性があるため査sa指摘により除外）を使わず、以下を候補とする。

### 候補1: 既存ローカル資産 `samples/e2e_sample.wav`

- 言語: 日本語（設定上ja想定）
- 長さ: **1.000秒**（実測: `ffprobe`、16kHz・1ch）
- 入手経路: 既存リポジトリ資産
- 評価: **CER/RTF実測には不十分**（作業指示書§2で既に指摘済みの事実を再確認）。単体動作確認（エラーなく推論が通るか）の用途に限り使用可能。

### 候補2: ドキュメント記載のYouTube URL（`docs/user-guides/configuration.md` L41）

- URL: `https://www.youtube.com/watch?v=QxnWrMasELQ`
- 言語: 日本語（実測確認: タイトル「【検証】電動キックボード 便利な一方で、クルマを運転中、超危険に感じる瞬間有りますよね！」）
- 長さ: **27:44（1664秒）**（実測: `yt-dlp --skip-download --print duration`。音声本体は未取得）
- 入手経路: 新規YouTube URL。ドキュメントの設定例に記載されたURLであり、実際の生産用`config/config.yaml`のデフォルト値ではないことを確認済み（実測: `config/config.yaml` L4のurlは別のGoogle Driveリンク）。
- 備考: 全長27分は比較試験には長すぎる可能性があるため、Phase1実測では冒頭数分を切り出す運用を推奨する（切り出し方の確定はPhase1実行計画側で行う）。

### 候補3: JSUT corpus（日本語音声コーパス、非YouTube）

- 言語: 日本語（女性話者、無響室録音の読み上げ音声）
- 長さ: 10時間（コーパス全体。個別ファイル単位で選択可能）
- 入手経路: 一次配布元 `https://sites.google.com/site/shinnosuketakamichi/publication/jsut`（東京大学 高道慎之介研究室）、ダウンロードURL `http://ss-takashi.sakura.ne.jp/corpus/jsut_ver1.1.zip`（version 1.1、2.7GB）
- ライセンス（一次資料引用）: テキストはCC-BY-SA 4.0等。音声データは「学術機関による研究」「非営利研究」「ブログ等を含む個人利用」での使用を許可。**再配布は不可**（"Re-distribution is not permitted, but you can upload a part of this corpus (e.g., ~100 audio files) in your website or blog."）。引用要求あり（Sonobe, Takamichi and Saruwatari, arXiv:1711.00354, 2017）。
- 評価: サンプリングレート48kHz・クリーンな読み上げ音声のため、CER測定のベースライン用途に適する。ただしYouTube動画（自然発話・雑音あり）とは音声特性が異なる点に留意。

### 推奨

候補2（YouTube、自然発話）と候補3（JSUT、クリーン読み上げ）を組み合わせ、候補1は動作確認用途に限定する案を推奨する。最終選定は計の確認を経ること。

## 5. Phase1実行計画

### 前提

本予備調査（§1-4）の結果、Phase1実測着手には以下が確定済みである:

- 実行環境: `venv-nemotron-poc/`（Transformers経路）および/または`venv-nemotron-poc-nemo/`（NeMo経路、上限`<3`指定必須）の隔離venv。生産用`.venv`・`pyproject.toml`・`uv.lock`は不変のまま。
- テスト音声: §4候補2・候補3（計承認後に確定）。

### 実行計画案

1. **環境構築**: §2の隔離venv作成コマンドを実行し、`python -c`によるimport確認のみ実施（軽量スモークテスト）。
2. **VRAM再実測**: `nvidia-smi`で空きVRAMを再確認。§3で確認した実測時点の空き2825MiBが不足する場合、他プロセス終了等でVRAM確保後に着手する。
3. **単発推論スモークテスト**: 候補1（`samples/e2e_sample.wav`、1秒）で最小動作確認（エラーなく文字起こし結果が返ること）。
4. **CER/RTF比較測定**: 候補2・候補3（計承認分）を対象に、以下を実測する。
   - 既存エンジン（Qwen3-ASR、`core/transcription_interface.py`の`Qwen3ASREngine`経由、生産用.venv使用）
   - 既存エンジン（Whisper、`WhisperTranscriptionEngine`経由、生産用.venv使用）
   - Nemotron-3.5-ASR-Streaming（隔離venv、単体スクリプト、生産コード非import）
   - 測定項目: CER（文字誤り率、参照テキストとの比較）、RTF（Real-Time Factor＝処理時間/音声長）、ピークVRAM使用量（`nvidia-smi`ポーリングまたは`torch.cuda.max_memory_allocated()`）
5. **出力形式案**: 3エンジン×候補音声数のマトリクス表（Markdown）。列: エンジン名／CER／RTF／ピークVRAM(MiB)／備考。比較結果は`00_レビュー依頼/作から計へのPhase1実測結果報告_YYYYMMDD.md`として作成する想定（実際のファイル作成はPhase1着手時）。
6. **NeMo経路の要否判断**: §1で確認した依存解決の不確実性（backtrack事例）を踏まえ、Transformers経路（`transformers>=5.13.0`）を主経路とし、NeMo経路は隔離環境構築に成功した場合のみ副次的に検証する案を推奨する。

### 未解決事項（計への確認事項）

- 候補2（YouTube、27分）を全尺使うか、冒頭切り出しにするかの方針
- 候補3（JSUT）を新規導入するか、候補2のみで足りるとするか
- VRAM空き容量（実測2825MiB）が不足した場合の対応方針（他プロセス終了の可否）

---

**セルフチェック完了宣言:**
私、作ロールは、以下の7項目チェックリストに基づきセルフチェックを実施し、すべての項目を満たしていることを宣言します。

1. 成果物（本報告書）は作成した
2. 命名規則は作業指示書§3のパス指定に一致（`REPORT`変数の命名規則どおり）
3. 5項目の見出しは作業指示書§3のgrepパターンと一致する形式（`## N. <パターン文字列>`）
4. 誤字脱字は確認済み
5. リンク切れ: 外部URLはすべてWebFetch/WebSearch/yt-dlpで実際にアクセス・実測した
6. スコープ外の作業（.venv変更・依存インストール・モデル実行）は一切含んでいない
7. （スクリプトではないため該当なし）

**署名**: 作ロール（saku）
**日付**: 2026年09月26日

## Git管理依頼

計ロールに以下のファイルのGit管理を依頼します:
- 00_レビュー依頼/作から計への予備調査完了報告_Nemotron3.5ASR-StreamingPhase1_20260926.md

変更内容: tc-ops #546 予備調査完了報告の新規追加

## WBS更新依頼

WBSの更新をお願いします。
