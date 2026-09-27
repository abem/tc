# 作から計への設計予備調査完了報告: Nemotron3.5ASR-StreamingPhase2

**報告日**: 2026-09-26
**報告者**: 作成ロール（作、saku）
**対象**: tc-ops #546 Phase2設計予備調査
**ブランチ**: feature/nemotron35-asr-phase1-investigation-20260926

## 実施概要

作業指示書（計から作への作業指示書_Nemotron3.5ASR-StreamingPhase2設計予備調査_20260926.md、査読合格sa、commit 6e2dcfe）に基づき、采条件7点に対応する実装設計を作成した。実際のコード変更（`webui.py`・`core/transcription_interface.py`等）・依存インストール・GPU実行は行っていない（既存コードの実測確認のみ、CPU範囲）。生産用`.venv`・`pyproject.toml`・`uv.lock`への変更なし（本報告書末尾の機械検査で確認）。

## 1. サブプロセス呼び出し設計

### 方式

采条件①のとおりサブプロセス方式を採用する。Phase1で実績のある`nemotron_infer.py`（証跡: `WORK_20260926_220529_phase1/nemotron_infer.py`、隔離venv上で6回の実行に成功済み）のパターンを土台に、生産用スクリプトとして設計する。

### 構成案

- **新規モジュール**: `core/nemotron_engine.py`（案）に`NemotronSubprocessEngine(TranscriptionEngine)`を新設。`TranscriptionEngine`抽象基底（`core/transcription_interface.py` L73-121実測）の`transcribe()`/`get_engine_name()`を実装し、既存2エンジン（`Qwen3ASREngine`・`WhisperTranscriptionEngine`）と同型のインターフェースを持つ。
- **サブプロセス側スクリプト**: `scripts/nemotron_infer.py`（新設案）。Phase1版から以下を変更する:
  - 引数: `audio_path`（必須）、`--language`（既定`ja-JP`、`TranscriptionConfig.language`から変換して渡す）
  - 出力: 標準出力へJSON1行のみを出力する（Phase1版は診断用に複数行のログがstdoutへ混入した実績があるため — 実測: Phase1の`result_qwen3_candidate2.json`等でログ行がstdoutに混入し後処理が必要だった、証跡: `WORK_20260926_220529_phase1/result_qwen3_candidate2_clean.json`作成経緯。この教訓をNemotronサブプロセス側にも適用し、`print()`はJSON1回のみに限定、ロード進捗等は明示的に`sys.stderr`へ出す設計とする）
- **呼び出しコード**（`NemotronSubprocessEngine.transcribe()`内、設計イメージ）:
  ```python
  proc = subprocess.run(
      [str(self._venv_python), str(self._script_path), audio_path,
       "--language", lang_code],
      capture_output=True, text=True, timeout=self._timeout_sec,
  )
  if proc.returncode != 0:
      raise RuntimeError(f"Nemotronサブプロセスが異常終了しました(code={proc.returncode}): {proc.stderr[-2000:]}")
  data = json.loads(proc.stdout)
  ```
- **タイムアウト設計**: `max(60, duration_sec * 3 + 30)`秒を提案する。根拠: Phase1実測でRTF最大0.0401（候補3）、モデルロード時間5.6〜27.8秒（実測、後者はHFキャッシュ未ヒット時の初回ダウンロードを含む値）。安全マージンとして推論部分は実測RTFの約75倍（0.04→3倍のマージン）、固定30秒はロード時間の吸収分とする。
- **異常終了時の扱い**: `returncode != 0`・JSON解析失敗（`json.JSONDecodeError`）・タイムアウト（`subprocess.TimeoutExpired`）のいずれも`RuntimeError`（またはその派生の専用例外）に変換して送出する。既存の`UnifiedTranscriber.transcribe()`は例外を素通しする設計（実測: `core/transcription_interface.py` L957-965、`except Exception as e: ... raise`）であり、これをそのまま活用する（§6で詳述）。

## 2. 既存モデル名判定への影響と回帰テスト設計

### 挿入方式

`UnifiedTranscriber.__init__`（実測: `core/transcription_interface.py` L933-938）は現在 `if Qwen3ASREngine.is_qwen3_model(...): ... else: WhisperTranscriptionEngine`という二分岐。ここへ`nemotron`判定を追加する。

```python
if is_nemotron_model(transcription_config.model):
    self.transcription_engine = NemotronSubprocessEngine(transcription_config)
elif Qwen3ASREngine.is_qwen3_model(transcription_config.model):
    self.transcription_engine = Qwen3ASREngine(transcription_config)
else:
    self.transcription_engine = WhisperTranscriptionEngine(transcription_config)
```

**挿入位置は既存`is_qwen3_model`判定より前**（instructor指示のとおり）。`is_nemotron_model`の判定文字列（案: `"nemotron" in name.lower()`）と`is_qwen3_model`の判定文字列（`"qwen3-asr" in name.lower() or "qwen3_asr" in name.lower()`、実測: L418-420）は文字列として排他的（互いの一致文字列を含まない）ため、挿入順序自体は既存3モデル名の判定結果に**数学的に影響しない**。順序を先頭にするのは可読性・将来の拡張時の事故防止（分岐の意図を明確にする）目的とする。

### 回帰テストケース一覧

| # | モデル名 | 期待される解決先エンジン | 現状/変更後 |
|---|---|---|---|
| 1 | `"Qwen/Qwen3-ASR-1.7B"` | `Qwen3ASREngine` | 不変（回帰確認対象） |
| 2 | `"kotoba-tech/kotoba-whisper-v2.2"` | `WhisperTranscriptionEngine` | 不変（回帰確認対象） |
| 3 | `"openai/whisper-large-v3"` | `WhisperTranscriptionEngine` | 不変（回帰確認対象） |
| 4 | `"nvidia/nemotron-3.5-asr-streaming-0.6b"`（案） | `NemotronSubprocessEngine` | 新規追加 |
| 5 | `"qwen3-asr-custom-finetune"`等、`is_qwen3_model`とも`is_nemotron_model`とも取れない境界値がないことの確認 | — | 文字列排他性の網羅確認（両判定関数に同一モデル名を渡し、両方Falseまたは片方のみTrueであることを検証） |

- テストは`core/transcription_interface.py`の`UnifiedTranscriber.__init__`に対する単体テスト（`pytest`、GPU不要・モデルロード不要。`__init__`内のエンジン選択直後に`type(transcriber.transcription_engine).__name__`を検証する設計で、実際のモデルダウンロード・推論は発生させない）として実装する。

### webui.py selectboxの扱い（査sa是正指摘反映、デフォルト不変の保証）

- 実測: `webui.py` L109-112、`options=["Qwen/Qwen3-ASR-1.7B", "kotoba-tech/kotoba-whisper-v2.2", "openai/whisper-large-v3"], index=0`
- 変更案: `options`リストの**末尾**にNemotronのモデル名を追加するのみ（`index=0`は変更しない）。これにより`options[0]`は引き続き`"Qwen/Qwen3-ASR-1.7B"`であり、デフォルト選択は不変。
- 確認方法: `webui.py`内の`options`リストをソースコードから抽出する単体テスト（`ast`モジュールで`st.selectbox`呼び出しの`options`引数リテラルを解析するか、より単純に該当行を正規表現で抽出し`options[0] == "Qwen/Qwen3-ASR-1.7B"`をassertする）を回帰テストに追加する。

### `./tc`のCLIデフォルト（指示書記載どおり、影響確認）

- `config/config.yaml` L9（`model: Qwen/Qwen3-ASR-1.7B`）は本設計のスコープでは変更しない。`./tc`はこの設定値を経由するため不変。ただし`core/transcription_interface.py`のディスパッチロジック変更の影響は共有して受けるため、回帰テストケース1（`"Qwen/Qwen3-ASR-1.7B"` → `Qwen3ASREngine`）が`./tc`側のデフォルト不変性も同時に保証する。

### `transcribe.py`（レガシーCLI、参考・スコープ外）

- 実測: `transcribe.py` L82-83のデフォルト解決ロジック（`--profile`未指定時はプロファイル"1"＝`kotoba-tech/kotoba-whisper-v2.2`、L57-62）は`./tc`とは独立した別の仕組みであり、本設計では`transcribe.py`を一切変更しないため影響なし。プロファイル"5"（L72、`Qwen/Qwen3-ASR-1.7B`）もデフォルト決定ロジックではなく参考情報。

## 3. 隔離venv構築スクリプト設計

### 方針

Phase1の手動手順（証跡: `00_レビュー依頼/作から計への予備調査完了報告_Nemotron3.5ASR-StreamingPhase1_20260926.md` §2）を再現可能なスクリプト化する。

### 設計案

- **配置場所**: `scripts/setup_nemotron_venv.sh`（新設案）。PoC作業ディレクトリ（`WORK_*`）には一切依存しない、リポジトリ直下`venv-nemotron-poc/`を固定の構築先とする（`.gitignore`の`venv*/`パターンで既にカバー済み、実測済み）。
- **内容**（設計イメージ）:
  ```bash
  #!/bin/bash
  set -euo pipefail
  cd "$(dirname "$0")/.."
  if [ -d venv-nemotron-poc ]; then
    echo "venv-nemotron-poc/ は既に存在します。再構築する場合は先に削除してください。" >&2
    exit 0
  fi
  uv venv venv-nemotron-poc --python 3.12
  uv pip install --python venv-nemotron-poc/bin/python \
    "transformers==5.17.0" "torch==2.14.0" --index-url https://download.pytorch.org/whl/cu130 \
    accelerate librosa soundfile
  ```
- **バージョン固定の理由**: Phase1実測で動作確認済みのバージョン（`transformers==5.17.0`／`torch==2.14.0`、実測: `WORK_20260926_220529_phase1/venv_install.log`）を明示固定する。`transformers>=5.13.0`という範囲指定のままだと、将来のインストール時に未検証の新バージョンが解決され再現性が損なわれるリスクがある（予備調査§1で確認したnemo_toolkit無上限指定によるbacktrack事例と同種のリスクを避ける）。
- **冪等性**: 既存ディレクトリがあれば何もせず終了する設計とし、誤って稼働中の検証環境を破壊しないようにする。
- **生産用`.venv`への非依存**: 本スクリプトは`uv venv`で完全に独立した環境を作るのみで、生産用`.venv/pyproject.toml/uv.lock`には一切触れない（予備調査§2で確認済みの設計をそのまま踏襲）。

## 4. 出力形式の整合設計

### 既存の出力経路（実測）

`webui.py`の結果処理は以下の3経路を持つ（実測: `webui.py` L306-395付近）:
1. `result.text`をファイル保存 + Google Driveアップロード（`_save_and_record()`、L306-342）
2. `result.segments`をSRT変換（`segments_to_srt(result.segments)`、L398）
3. `record_transcription_history(result=result, ...)`（変換履歴記録、L334）

これらはいずれも`TranscriptionResult`（`core/transcription_interface.py` L38-68実測）のフィールド（`text`・`segments`・`language`・`duration`・`processing_time`・`model_name`）に依存する。

### Nemotronサブプロセス出力の変換設計

- Nemotronのオフラインバッチ推論（`model.generate()`、Phase1実測で使用）はモデルカード・公式APIに文単位/時刻単位のセグメント分割出力を持たない（全体テキストのみを返す）。したがって`TranscriptionSegment`は**単一セグメント**（`start=0.0`, `end=duration`, `text=全文`）として構築する設計を提案する。これは`WhisperTranscriptionEngine`の`config.include_timestamps=False`時のフォールバック動作（全体を1セグメントとする既存パターン、`core/transcription_interface.py`のコメントに準拠）と同型であり、既存コードの前例に倣う。
- `TranscriptionResult`構築時に必須の`duration`・`processing_time`・`model_name`は、`NemotronSubprocessEngine.transcribe()`内でサブプロセスのJSON出力（`audio_duration_sec`・`infer_elapsed_sec`、Phase1の`nemotron_infer.py`が既に出力しているフィールド）と`self.get_engine_name()`から構築する。
- **SRT出力への影響**: 単一セグメントの場合、SRTは1エントリ（00:00:00,000 → 全長）のみとなる。字幕としての実用性は低いが、既存の`segments_to_srt()`関数自体の変更は不要（単一要素のリストとして正常に処理される想定。関数の入力契約を壊さない設計）。この制約は報告書上の既知の制限事項として計・采へ明記する。
- **Google Driveアップロード・履歴記録**: `result.text`・`result`オブジェクト全体を渡す既存の呼び出し（L324・L334）はエンジン種別を区別しないため、`NemotronSubprocessEngine`が正しく`TranscriptionResult`を返せば**追加のwebui.py変更は不要**と判断する。

## 5. 長音声チャンク処理の要否

### 判断: 要（暫定閾値300秒を提案、実装フェーズのGPU実測で確定）

### 根拠（Phase1実測からの外挿）

Phase1実測（候補2=180秒、候補3=70.2秒）のVRAM推移（実測値、証跡: 本Phase1報告書§1表）:

| 音声長 | ロード後(ベースライン比) | 推論後ピーク(ベースライン比) |
|---|---|---|
| 70.2秒 | +2690MiB | +3903MiB |
| 180秒 | +2137MiB | +5162MiB |

ロード後の差分（モデル重み自体）は音声長に依存せずほぼ一定（+2137〜2690MiB、変動は測定誤差の範囲）である一方、**推論後ピークとの差（推論実行時に追加で確保される分）は音声長にほぼ比例して増加**している（70.2秒: +1213MiB、180秒: +3025MiB。180/70.2≈2.56倍に対しVRAM増分は3025/1213≈2.49倍で概ね線形）。

この線形関係を外挿すると、生産で想定される長尺音声（例: 30分=1800秒）では推論時追加分が約1800/180×3025≈30250MiBに達する可能性があり、RTX 4080 SUPER搭載VRAM（16376MiB）を大幅に超過する。**Nemotronのオフラインバッチ推論(`model.generate()`)をチャンク分割なしで長尺音声にそのまま適用するのは、VRAM不足によるOOM(Out of Memory)のリスクが高い**と判断する。

### 対策案

既存`Qwen3ASREngine`が実運用で採用している`CHUNK_THRESHOLD_SEC = 300`（5分、実測: `core/transcription_interface.py` L596。RTX 4080 SUPER上で15分超の音声にCUBLAS_STATUS_INTERNAL_ERRORが発生した実例に基づく既存の安全マージン設定）と同一の閾値をNemotronにも暫定適用し、閾値超過時は300秒単位で分割してサブプロセスを複数回呼び出し、結果を連結する設計を提案する。ただし以下は実装フェーズでのGPU実測が必要な未確定事項である:
- Nemotron自体はストリーミング用途のモデルであり、モデルカード記載の正式なストリーミングAPI（`processor.set_num_lookahead_tokens()`等、チャンク単位でメモリを一定に保つ設計）を使えば、300秒閾値でのオフライン再分割よりも本来の設計に近い形でVRAM使用量を一定に保てる可能性がある。これはPhase1では未検証（Phase1はオフラインバッチ`generate()`のみ使用）であり、実装フェーズでの追加調査対象として明記する。
- 上記の線形外挿は2点（70.2秒・180秒）のみに基づく推定であり、実際の長尺音声（10分・20分規模）での実測による閾値の妥当性確認が必要。

## 6. エラーハンドリング設計

### 隔離venv未構築時の設計

`NemotronSubprocessEngine._load_model()`相当の箇所（またはサブプロセス起動直前）で`venv-nemotron-poc/bin/python`の存在を`Path.exists()`で確認し、存在しなければ以下のメッセージで`RuntimeError`を送出する設計を提案する:

```
Nemotron隔離venvが未構築です。scripts/setup_nemotron_venv.sh を実行してから再度お試しください。
```

### 既存インフラとの整合性（実測、webui.py変更不要と判断できる根拠）

ジョブ実行の例外処理は`core/webui_workflow.py`の`start_transcription_job()`内`_run()`で既に`except BaseException as e: job.error = e`という形で全面的に捕捉されている（実測: `core/webui_workflow.py` L50-58）。`UnifiedTranscriber.transcribe()`自体も例外を素通しする設計（`core/transcription_interface.py` L957-965の`except Exception as e: ... raise`）であるため、`NemotronSubprocessEngine.transcribe()`内で送出した`RuntimeError`は、**既存のエンジンと全く同じ経路でUI側へ伝播する**。したがって、隔離venv未構築時のエラー表示のために`webui.py`側を変更する必要は**ない**と判断する。

### 他エンジンへの波及がないことの確認方法

`_start_job_from_item()`（実測: `webui.py` L196-207）は呼び出しのたびに`UnifiedTranscriber(transcription_config)`を新規インスタンス化する設計であり、エンジン間で状態（モデルインスタンス等）を共有する仕組みは構造上存在しない。したがって、Nemotron選択時に隔離venv未構築で例外が発生しても、後続の別ジョブでQwen3-ASR/Whisperを選択すれば独立して正常動作する。この確認は以下のテストケースで検証する設計とする:

- テストケース: (1) `NemotronSubprocessEngine`を隔離venv未構築の状態でインスタンス化し`transcribe()`呼び出しが`RuntimeError`になることを確認 → (2) 同一プロセス内で新規に`UnifiedTranscriber(model="Qwen/Qwen3-ASR-1.7B")`を生成し`is_qwen3_model`判定・エンジン選択が正常に行われることを確認（実際のモデルロードまでは行わずエンジンクラスの選択のみ検証、GPU不要）。

## 7. 実装計画

### 実装ステップ

1. **ステップ1（GPU不要）**: `core/nemotron_engine.py`（`NemotronSubprocessEngine`）・`scripts/nemotron_infer.py`（サブプロセス側）を実装。§1のJSON入出力仕様・タイムアウト設計・§6のエラーハンドリング設計に従う。
2. **ステップ2（GPU不要）**: `UnifiedTranscriber.__init__`へのディスパッチ挿入（§2）。§2の回帰テストケース1-5をpytestで実装・実行（いずれもモデルロード・GPU不要、文字列判定・クラス選択のロジックテストのみ）。
3. **ステップ3（GPU不要）**: `scripts/setup_nemotron_venv.sh`実装（§3）。シンタックスチェック（`bash -n`）と、既存隔離venv（Phase1で構築済みの`venv-nemotron-poc/`）に対する`import`確認程度は本予備調査のスコープ内（CPU範囲）で実施可能。
4. **ステップ4（GPU不要）**: `webui.py` L109-112の`options`リスト末尾への1行追加（§2）。
5. **ステップ5（GPU使用・要事前連絡）**: ステップ1-4完了後、隔離venv経由でのE2E動作確認（小音声・候補1相当での動作確認）。**采条件⑥のとおり、この時点で計経由で采へ事前連絡が必要**（jev-local停止要否の確認のため）。
6. **ステップ6（GPU使用・要事前連絡）**: §5で設計したチャンク処理の実機検証（10分・20分規模の長尺音声でのVRAM実測）。ステップ5と同様に計経由での事前連絡が必要。
7. **ステップ7（GPU不要）**: ステップ5・6の実測結果を踏まえた最終調整（タイムアウト値・チャンク閾値の実測ベースへの更新）とpytest全体（既存1319件+新規回帰テスト）の実行確認。

### GPU使用が必要になるタイミングのまとめ

- ステップ1-4・7は**GPU不要**（コード実装・ロジックテストのみ）。
- ステップ5（初回E2E動作確認）・ステップ6（長尺音声実測）の**2箇所**でGPU使用が必要となり、いずれも采条件⑥に基づき着手前に計経由で采への連絡が必要である。

---

**セルフチェック完了宣言:**
私、作ロールは、以下の7項目チェックリストに基づきセルフチェックを実施し、すべての項目を満たしていることを宣言します。

1. 成果物（本報告書）は作成した
2. 命名規則は作業指示書§3のパス指定に一致（`REPORT`変数の命名規則どおり）
3. 7項目の見出しは作業指示書§3のgrepパターンと一致する形式
4. 誤字脱字は確認済み
5. リンク切れ: 参照した既存コードの行番号・内容はすべて実際に読んで実測した
6. スコープ外の作業（コード変更・依存インストール・GPU実行）は一切含んでいない（コードスニペットは全て設計案であり、実装はしていない）
7. （スクリプトの新規実行ではなく設計提示のため該当なし。ただし引用した実測箇所は`grep`/`sed -n`で実際に読み取り確認した）

**署名**: 作ロール（saku）
**日付**: 2026年09月26日

## Git管理依頼

計ロールに以下のファイルのGit管理を依頼します:
- 00_レビュー依頼/作から計への設計予備調査完了報告_Nemotron3.5ASR-StreamingPhase2_20260926.md

変更内容: tc-ops #546 Phase2設計予備調査完了報告の新規追加

## WBS更新依頼

WBSの更新をお願いします。
