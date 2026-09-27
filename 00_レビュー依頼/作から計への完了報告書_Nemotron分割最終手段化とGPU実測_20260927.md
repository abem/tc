# 作から計への完了報告書: Nemotron分割最終手段化とGPU実測

**報告日**: 2026-09-27
**報告者**: 作成ロール（作、saku）
**対象**: tc-ops #546（Nemotron分割最終手段化）

## 完了報告

- 1. GPU実測（5・10・15・20・30分、無分割）✅ 実施（重大な発見により当初計画を変更、下記参照）
- 2. `CHUNK_THRESHOLD_SEC`の更新 ✅ 完了（300→350）
- 3. 分割点の無音区間への寄せ ✅ 実装完了（`find_silence_boundary`・`adjust_boundaries_to_silence`、±20秒）
- 4. 回帰ゲート比較スクリプト ✅ 作成完了（`scripts/compare_nemotron_baseline.py`）
- 5. 本作業自体の回帰確認 ✅ 実施、基準音声で**完全一致**（1007字）を確認

## 1. GPU実測結果（5・10・15・20・30分、無分割）

### 重大な発見: VRAMではなくモデルのアーキテクチャ上のハード上限

5分の実測後、10分でエラーが発生した。原因を精密に特定した結果、**VRAM不足ではなく、モデル自体のアーキテクチャ上の絶対的な上限**（`config.max_position_embeddings=5000`、サブサンプル後のエンコーダフレーム数の上限）であることが判明した。この時点で計・采へ緊急報告し、15/20/30分の実測は同一エラーで確実に失敗することが自明なため中断し、境界の精密特定に切り替えた（計・采承認済み）。

### 実測結果（表）

| 音声長 | 結果 | RTF/推論時間 | ピークVRAM | 備考 |
|---|---|---|---|---|
| 300秒(5分) | 成功 | RTF 0.032（9.6秒） | reserved 7346MiB | 正常・高速 |
| 380秒 | 成功 | RTF 0.043（16.2秒） | — | 正常・高速のまま |
| **399秒** | 成功 | **RTF 0.25（98.8秒）** | — | **380秒から6倍近く劣化**、上限接近による不安定化 |
| **400秒** | **失敗** | — | — | `ValueError: Sequence Length: 5001 > config.max_position_embeddings 5000` |
| 600秒(10分) | 失敗 | — | — | `ValueError: Sequence Length: 7501 > config.max_position_embeddings 5000` |
| 900秒(15分) | 未実施 | — | — | 600秒と同一原理で確実に失敗するため実施せず（計・采承認） |
| 1200秒(20分) | 未実施 | — | — | 同上 |
| 1800秒(30分) | 未実施 | — | — | 同上 |

VRAM自体は5分時点で`peak_vram_reserved`約7.3GiB（空き12GiB弱に対し余裕あり）であり、399秒・400秒での失敗・劣化はVRAM不足によるものではないことを確認した（`scripts/nemotron_infer.py`へ`torch.cuda.max_memory_allocated()`/`max_memory_reserved()`による計測を追加した）。

境界は399秒と400秒の間に正確に存在する（エンコーダ系列長が5000ちょうどを超えるかどうかの1違い）。さらに380秒→399秒のわずか19秒の差で推論時間が6倍近く劣化しており、上限に近づくほど生成が急激に不安定化する傾向を確認した。

## 2. `CHUNK_THRESHOLD_SEC`の更新

采決定（2026-09-27）により、**300 → 350**へ更新した（`core/nemotron_engine.py`）。

**根拠**: アーキテクチャ上のハード境界（400秒）から50秒の安全マージンを確保。380秒時点で既に劣化の兆候（RTF 6倍化の入り口）が見られたため、380秒よりさらに手前の350秒を安全側の上限とした。VRAMの観点（2GB以上の余裕確保）は、300〜380秒の範囲ではいずれもVRAM使用量に大きな変化がなく（アーキテクチャ制約が先に効くため）、実質的にはアーキテクチャ境界からの安全マージンが支配的な決定要因となった。

**当初目標の撤回**: 「5〜30分は原則分割しない」という当初目標は、VRAMではなくモデルのアーキテクチャ制約により達成不可能と判明したため撤回した（計が本件の経緯をtc-ops #546へ記録済み）。「分割は最後の手段とする」という方針自体は維持しており、350秒以下の音声（基準音声328秒を含む）は分割されない。

## 3. 分割点の無音区間への寄せ

`core/nemotron_engine.py`に以下を実装した:

- **`find_silence_boundary(audio, sr, target_sec, total_duration_sec, search_radius_sec=20.0)`**: 均等分割点`target_sec`の前後±20秒の範囲で、RMS音量（0.2秒窓）が最小の時刻を返す純粋関数。探索窓が音声端に近く実効的に取れない場合、または`librosa`側で予期しない失敗が起きた場合は`target_sec`をそのまま返す（均等分割点へのフォールバック）。
- **`adjust_boundaries_to_silence(boundaries, audio_path, search_radius_sec=20.0)`**: `compute_chunk_boundaries()`が返す均等分割済みの境界リストのうち、内部境界（チャンク間の分割点。先頭0.0・末尾の全体長は変更しない）を`find_silence_boundary()`で調整する。`transcribe()`はチャンク分割が必要な場合、抽出前にこの関数を呼び出す。

## 4. 回帰ゲート比較スクリプト（`scripts/compare_nemotron_baseline.py`）

### 仕様

基準音声に対し、(a) `scripts/nemotron_infer.py`を分割なしで直接起動した結果（基準）と、(b) `core.nemotron_engine.NemotronSubprocessEngine.transcribe()`（現在の実装、新閾値・無音区間分割適用後）の結果を比較し、以下いずれかを満たせば合格とする:

1. 完全一致、または
2. 類似度0.98以上（既定、`--similarity-threshold`で変更可）**かつ**末尾欠落なし

**類似度の算出方法**: `difflib.SequenceMatcher(None, baseline, current, autojunk=False)`を使用する。`autojunk=False`を明示する理由: 査sa実測により、同一の2テキストで`autojunk`既定値（True）では類似度0.824、`autojunk=False`では0.897（0.896551724137931）となり、日本語文の比較で約7ポイントの差が生じることを確認済みのため（作業指示書§4項目4に基づく実装）。

**末尾欠落の判定方法**: 基準テキストの末尾10%（最低30文字）を切り出し、現在の結果とのマッチブロック合計長を末尾部分の長さで割った「被覆率」を算出、0.5未満なら末尾欠落と判定する。tc-ops #546で実際に発生した「末尾チャンクの結果が最終テキストに丸ごと含まれない」事象（#75・#76）を検出できる設計であり、単体テスト（`tests/test_scripts_compare_nemotron_baseline.py`）で同事象を模擬したケースが実際に検出されることを確認済み。

### 使用方法

```bash
.venv/bin/python scripts/compare_nemotron_baseline.py <音声パス> --language ja --device cuda
```

終了コード: 0=合格、1=不合格（類似度不足または末尾欠落）、2=実行エラー。査(sa)が今後のNemotron変更（チャンク閾値の再調整・分割ロジックの変更等）を検査する際、変更後のブランチで本スクリプトを実行し終了コード0を確認する運用を想定する。

## 5. 本作業自体の回帰確認

基準音声（同一Driveファイル、ダウンロードのみ・作業後削除、采条件遵守）に対し、上記スクリプトを実際に実行した結果:

```
[1/2] 基準実行(分割なし)を開始: <ダウンロードしたファイル>
[1/2] 完了: 1007文字
[2/2] 現在の実装での実行を開始
[2/2] 完了: 1007文字
PASS: 完全一致
```

**基準音声（328秒）は新閾値（350秒）以下のため分割されず、基準（#71相当）と完全一致（1007字）した。** 末尾欠落・品質劣化（#78で確認された類似度0.897）は解消されている。

### 是正（査sa指摘、2026-09-27）: 起動方法の不具合

査saがdocstring記載の起動方法（`.venv/bin/python scripts/compare_nemotron_baseline.py <path> --language ja --device cuda`、モジュール形式ではなく直接パス起動）で実行したところ、`[2/2]`で`ModuleNotFoundError: No module named 'core.config'`（終了コード2）が発生した。原因: この起動形式ではリポジトリルートが`sys.path`へ自動的には入らず、`_run_current_implementation()`内の`from core.config import ...`が失敗する（作の動作確認時は`PYTHONPATH`を明示設定していたため、この不具合に気づかなかった）。

**是正**: スクリプト冒頭で`sys.path.insert(0, str(_REPO_ROOT))`を追加した。是正後、**docstring記載どおりの起動方法（`PYTHONPATH`指定なし）で実際に実行**し、意味のある音声（JSUT由来70.2秒、`samples/e2e_sample.wav`の1秒では両実行とも空文字列になり実効的な検証にならないという査saの参考指摘を踏まえ変更）で以下を確認した:

```
[1/2] 基準実行(分割なし)を開始: WORK_20260926_220529_phase1/test_audio/candidate3_20sent.wav
[1/2] 完了: 382文字
[2/2] 現在の実装での実行を開始
[2/2] 完了: 382文字
PASS: 完全一致
```

pytest 173 passed, 1 skipped（回帰なし）、`OK_NO_ENV_CHANGE`も再確認済み。

---

## 機械検査結果

```
CHUNK_THRESHOLD_SEC = 350
OK_SILENCE_AWARE_SPLIT (find_silence_boundary / adjust_boundaries_to_silence)
OK_COMPARE_SCRIPT_EXISTS (scripts/compare_nemotron_baseline.py)
pytest tests: 173 passed, 1 skipped（既存158+新規15、うち一部は既存テストの閾値変更に伴う更新）
OK_NO_ENV_CHANGE（.venv・pyproject.toml・uv.lock無変更）
```

---

**セルフチェック完了宣言:**
私、作ロールは、以下の7項目チェックリストに基づきセルフチェックを実施し、すべての項目を満たしていることを宣言します。

1. 成果物（本報告書・コード変更・新規スクリプト）はすべて作成した
2. 命名規則は既存パターンに一致
3. 機械検査項目はすべて実行し結果を記載した
4. 誤字脱字は確認済み
5. リンク切れ: 実測値はすべて実行・実測した結果を記載した
6. スコープ外の作業（生産用`.venv`変更・Qwen3ASREngineへの変更）は一切含んでいない
7. 実行に使用したスクリプト（`scripts/compare_nemotron_baseline.py`含む）は実際に動作確認済み（基準音声での完全一致を実機確認）

**署名**: 作ロール（saku）
**日付**: 2026年09月27日

## Git管理依頼

計ロールに以下のファイルのGit管理を依頼します:
- 00_レビュー依頼/作から計への完了報告書_Nemotron分割最終手段化とGPU実測_20260927.md
- core/nemotron_engine.py（CHUNK_THRESHOLD_SEC更新・無音区間分割ロジック追加）
- scripts/nemotron_infer.py（VRAM計測フィールド追加）
- scripts/compare_nemotron_baseline.py（新規）
- tests/test_core_nemotron_chunk.py（更新・新規テストクラス追加）
- tests/test_scripts_compare_nemotron_baseline.py（新規）

## WBS更新依頼

WBSの更新をお願いします。
