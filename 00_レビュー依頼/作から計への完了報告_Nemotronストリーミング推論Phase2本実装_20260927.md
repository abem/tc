# 作から計への完了報告: Nemotronストリーミング推論Phase2本実装

**報告日**: 2026-09-27
**報告者**: 作成ロール（作、saku）
**対象**: tc-ops #546（Phase2本実装、作業指示書commit 3b4dbad、査sa合格済み）

## 実施概要

承認済みキックオフ計画に基づき実装・単体テスト（GPU不要範囲）を行い、その後kei経由で采承認を得たうえでGPU実測（回帰ゲート4条件）を実施した。着手前にWebUIアイドル状態・GPU使用状況（19%、6196MiB、kei報告のベースラインと一致）を確認済み。

**訂正（査sa品質検査で不合格・是正済み）**: 初版では、streaming経路（`_run_streaming_inference()`/`_build_streaming_chunk_generator()`）が`main()`で解決済みの`language_arg`を一切受け取らず、`processor(...)`呼び出しに`language`を渡していなかった（オフラインバッチ経路は従来から正しく渡していた）。この結果、`--language ja-JP`等を明示指定してもstreaming経路のみ常にNemotronの既定値`"auto"`（自動言語判定）に落ちる設計欠落があった。sa指摘を受け、両関数へ`language`引数を追加し`processor(...)`へ明示的に渡すよう是正した。回帰テスト（`tests/test_core_nemotron_language.py::TestStreamingLanguagePropagation`、2件）を追加し、明示指定（`en-US`）・既定値（`auto`）ともにstreaming経路の`processor(...)`呼び出しへ正しく伝播することを検証した（pytest 182 passed、1 skipped）。

**下記「回帰ゲート4条件のGPU実測結果」のうち条件1・3・4は是正前後で変化しない（350秒以下のオフライン経路・pytest・Qwen3回帰は本是正の影響範囲外）。条件2のCER比較は、采指示により`language`対称性（streaming側・分割方式側とも明示的に同一の`"ja-JP"`）を明記のうえ再測定した（下記は再測定後の値）。**

### 条件2再測定（言語対称性の確認、2026-09-27、采指示）

是正前の初回測定はstreaming側が実質`"auto"`で動作しており、分割方式側（明示的に`"ja-JP"`）と非対称な条件だった。是正後、両経路とも`engine._resolve_language()`の同一戻り値（明示的な`"ja-JP"`）を使用して再測定した:

| 経路 | lang_code | 文字数 | 正規化CER |
|---|---|---|---|
| streaming | ja-JP（明示、伝播確認済み） | 2495（是正前と同一） | **13.49%**（是正前と同一） |
| 分割方式(旧経路) | ja-JP（明示） | 2536（変化なし） | 13.73%（変化なし） |

**言語対称性を確保した条件下でも、CER・文字数とも是正前の測定値と完全に一致した。** これは、このJSUT日本語音声では`"auto"`判定でも正しく`"ja-JP"`相当の結果が得られていたことを裏付けるものであり、当初の「streamingが分割方式に劣らない」という結論に変更はない。処理時間はstreaming側で31.9秒（前回27.3秒、run-to-runの変動範囲内）、VRAMは前回と同一（2501.7MiB/2558.0MiB）だった。分割方式は変化なし（11.75秒→12.32秒、VRAM同一）。

## 実装内容

### 1. `scripts/nemotron_infer.py`

- `--streaming`/`--num-lookahead-tokens`（既定13）フラグを追加。
- `_build_streaming_chunk_generator()`（新設）: 音声を`processor.num_samples_first_audio_chunk`/`num_samples_per_audio_chunk`で刻み、`processor(..., is_streaming=True, ...)`でmelチャンクを生成する。理論値と実際のSTFTフレーム数が±1ずれるケース（ストリーミング推論スパイクで確認済み）への防御として、各チャンクを要求フレーム数(`num_mel_frames_first_audio_chunk`/`num_mel_frames_per_audio_chunk`)へ明示的に切り詰め/ゼロ埋めする。
- `_run_streaming_inference()`（新設）: 上記ジェネレータを`model.generate(input_features=..., num_lookahead_tokens=...)`へ渡し、1回の呼び出しで音声全体を処理する。実験的API呼び出しは本関数・本ファイルに閉じ込め、`core/nemotron_engine.py`側は関与しない。
- `main()`に`--streaming`分岐を追加（既存のオフラインバッチ用ループは無変更、`else`節へ移動しただけ）。結果は既存の`chunks`配列形式（要素数1）に揃え、呼び出し元のパース処理をそのまま再利用できるようにした。

### 2. `core/nemotron_engine.py`

- `STREAMING_NUM_LOOKAHEAD_TOKENS = 13`を追加。
- `_invoke_subprocess()`に`streaming: bool = False`引数を追加し、`True`時に`--streaming --num-lookahead-tokens 13`を付与する。
- `transcribe()`を、`duration_sec > CHUNK_THRESHOLD_SEC`（350秒）の場合にまずstreaming推論（`streaming=True`、単一ファイル・分割なし）を試み、例外発生時は`logger.warning("Streaming推論が失敗、分割方式へフォールバック: ...")`（指示書指定の一意な文言、変更なし）を出したうえで既存の均等分割＋無音区間調整方式へフォールバックする構造へ変更した。350秒以下は完全に無変更（既存の`else`節、コードパスに一切触れていない）。
- `compute_chunk_boundaries`・`find_silence_boundary`・`adjust_boundaries_to_silence`は削除せずフォールバック用に維持。

### 3. 回帰テスト（`tests/test_core_nemotron_chunk.py`）

- 新設`TestStreamingDispatch`: (a) 350秒超でstreaming成功時は分割・チャンク抽出を一切行わないこと、(b) streaming失敗時に一意な文言でログ警告を出し分割方式へフォールバックすること、の2テスト。
- 既存の長音声チャンク処理テスト3件（`test_long_audio_splits_extracts_chunks_single_call_joins_with_space`等、いずれもfake_duration>350）の`_invoke_subprocess`モックへ`streaming`引数を追加し、`streaming=True`時は例外を送出してフォールバック経由で従来の分割挙動を検証する形へ更新（新シグネチャとの整合性確保）。

## 完了条件（機械検査）実測結果

```
$ grep -n "num_lookahead_tokens" scripts/nemotron_infer.py
（_run_streaming_inference定義・set_num_lookahead_tokens呼び出し・main()内の使用箇所を確認）

$ grep -q "Streaming推論が失敗、分割方式へフォールバック" core/nemotron_engine.py && echo OK_FALLBACK_LOG_PRESENT || echo MISSING_FALLBACK_LOG
OK_FALLBACK_LOG_PRESENT

$ grep -n "num_samples_first_audio_chunk\|num_samples_per_audio_chunk\|frame.*adjust\|padding\|truncat" scripts/nemotron_infer.py
（_build_streaming_chunk_generator内で使用していることを確認）

$ uv run python -m pytest tests -q 2>&1 | tail -5
180 passed, 1 skipped, 3 warnings in 12.51s

$ git diff --name-only -- .venv pyproject.toml uv.lock | wc -l
0 → OK_NO_ENV_CHANGE
```

`git diff --summary`でexec bit変更もないことを確認済み。

## 回帰ゲート4条件のGPU実測結果

着手前GPU状態（kei報告のベースラインと一致確認）: 使用率19%、6196MiB使用（総量16376MiB）。

### 条件1: 基準通話音声(328秒)で現行と完全一致

`NemotronSubprocessEngine.transcribe()`（本番API、実装後のコード）をそのまま呼び出した:

```
metadata: {"chunked": false, "chunk_count": 1, "failed_chunks": 0, "empty_chunks": 0}
char_count: 1007
```

**328秒は350秒以下のためオフライン経路のまま処理され（`chunked=False`）、既存の確立済み基準（#71系統、1007字）と完全一致した。** 350秒以下のコードパスが本実装で一切変更されていないことをコードレベルだけでなく実機でも確認できた。

### 条件2: 350秒超の音声でstreaming出力が現行の分割方式より劣らないこと(正規化CER比較)

JSUT基本文コーパス（`basic5000`）から113文を無音0.3秒区切りで連結した非本番音声（485.5秒、350秒を明確に超える）を作成し、参照テキストと突合した。

| 経路 | 文字数 | 正規化CER |
|---|---|---|
| streaming(本実装、num_lookahead_tokens=13) | 2495 | **13.49%** |
| 分割方式(旧経路、均等分割+無音区間調整、fallback相当を明示実行) | 2536 | 13.73% |

**streamingのCER(13.49%)は分割方式(13.73%)を下回り、「劣らない」ことを実測で確認した（むしろわずかに改善）。**

### 条件3: 処理時間・ピークVRAM実測

| 経路 | 推論時間 | RTF | peak_vram_allocated | peak_vram_reserved |
|---|---|---|---|---|
| streaming | 27.31秒 | 0.056 | **2501.7MiB** | 2558.0MiB |
| 分割方式(旧経路) | 11.75秒(2チャンク合計) | 0.024 | 4853.9MiB | 7172.0MiB |

**トレードオフ**: streamingは推論時間が分割方式の約2.3倍だが（Python側のチャンクループ・逐次generate()のオーバーヘッドによるものと推測）、ピークVRAMは分割方式の約半分(2502MiB vs 4854MiB)に収まる。両経路とも485秒の音声に対して数十秒での処理であり、実時間比(RTF)は十分に1を下回る。VRAM総量16376MiBに対し、いずれも十分な余裕がある。

### 条件4: 既存テスト全件合格・Qwen/Whisperへの回帰なし

```
$ uv run python -m pytest tests -q 2>&1 | tail -5
180 passed, 1 skipped, 3 warnings in 12.51s
```

Qwen3-ASR(JSUT候補3、生産用.venv)を実行し、本実装着手前と同一の結果(424字)が得られることを確認した(Whisperは今回未使用のためテストのみで確認、Nemotronの変更が別プロセス/隔離venvで完結するため構造的に非干渉)。

## フォールバック動作の確認

`tests/test_core_nemotron_chunk.py::TestStreamingDispatch::test_streaming_failure_falls_back_to_split_with_warning_log`（単体テスト、モックでstreaming呼び出しを`RuntimeError`で意図的に失敗させる）で、以下を確認済み:

- `_invoke_subprocess`が2回呼ばれる(1回目: streaming失敗、2回目: 分割方式で成功)。
- `caplog`で`"Streaming推論が失敗、分割方式へフォールバック"`という指示書指定の一意な文言がログに出力されることを確認。
- 分割方式のチャンク抽出(`_extract_chunk_wav`)が実際に呼ばれ、結果テキストが正しく結合されること。

## 既知の制限事項

- ストリーミングAPIは transformers公式ドキュメントに`"experimental feature"`と明記されている。将来のtransformersバージョンアップでAPIが変更される可能性がある(依存分離により影響範囲は`scripts/nemotron_infer.py`内に限定される設計)。
- 本実装のGPU実測は非本番JSUT連結音声(485秒、1パターン)でのCER比較にとどまる。より多様な音声(異なる話者・雑音条件等)での精度傾向は未検証。
- streamingは分割方式よりVRAM使用量は少ないが推論時間は長い(約2.3倍)というトレードオフがある。今回の音声長(485秒)では両経路とも実用上問題ない範囲だが、より長い音声でこの時間差がどう推移するかは未検証。

## 後片付け

- ダウンロード音声・JSUT連結音声・仮説テキストファイルはすべて削除済み。証跡:
  ```
  $ rm -fv .../phase2_baseline_328s.mp3 .../jsut_long_reference.wav .../jsut485_streaming_hyp.txt .../jsut485_split_hyp.txt
  removed '.../phase2_baseline_328s.mp3'
  removed '.../jsut_long_reference.wav'
  removed '.../jsut485_streaming_hyp.txt'
  removed '.../jsut485_split_hyp.txt'
  $ ls .../*.mp3 .../*.wav
  ls: cannot access ...*.mp3: No such file or directory
  ls: cannot access ...*.wav: No such file or directory
  ```
- 実測後GPU状態: 使用率14%、5394MiB使用(着手前6196MiBから増加なし、リーク懸念なし)。

---

## Git管理依頼

計ロールに以下のファイルのGit管理を依頼します:
- core/nemotron_engine.py
- scripts/nemotron_infer.py
- tests/test_core_nemotron_chunk.py
- 00_レビュー依頼/作から計への完了報告_Nemotronストリーミング推論Phase2本実装_20260927.md

## WBS更新依頼

WBSの更新をお願いします。

## GPU使用完了報告

tc-ops #546 Phase2本実装のGPU実測はすべて完了しました。jev-local再開可を采へ報告してよいか、計の判断をお願いします。
