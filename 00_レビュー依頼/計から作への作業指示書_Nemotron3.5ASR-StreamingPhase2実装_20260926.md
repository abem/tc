# 計から作への作業指示書_Nemotron3.5ASR-StreamingPhase2実装_20260926

## 1. DoR (Definition of Ready) チェック

- [x] 1. 背景と目的が明確か
- [x] 2. ゴール（完了条件）が定義されているか（機械検査 exit 0 で判定可能か）
- [x] 3. スコープ（範囲）が限定されているか
- [x] 4. 成果物の仕様・要件が明確か
- [x] 5. 依存関係が解決されているか（Phase2設計予備調査で確定済み）
- [x] 6. 担当者と期限が設定されているか（担当: saku、期限: 2026-09-28）
- [x] 7. レビュー/承認者が明確か（査読=査(sa)、最終承認=計(kei)）

**発行前の追加検証（正典: 06d_operations.md「5.1 検査健全性の原則」規則1・規則5／ADR-010）**

- [x] 8. 検査コマンド自身が結果に混入しないことを検証したか（規則1）: §3の判定はpytest実行結果・ファイル存在・grepによる構造チェックであり、検査コマンド自身がテスト対象コードに混入することは構造上ない。
- [x] 9. 現況把握に必要な実測項目を網羅して提供したか（規則5）: Phase2設計予備調査完了報告（saku作成・sa検査合格）の設計内容と、計が追加実測したタイムスタンプ機構の実装箇所を下記§6に列挙した。

## 2. 背景と目的

tc-ops #546 Phase2設計予備調査（saku作成・sa検査合格・commit 509e7ab）により、Nemotron-3.5-ASR-Streamingをサブプロセス経由でWebUIに追加する設計が確定した。本指示書は、その設計に基づく**実装（コード変更）とGPU不要な範囲でのテスト**を対象とする。

**追加決定事項（采指摘対応、tc-ops #546記録済み）**: WebUIの`include_timestamps`（タイムスタンプ付与、SRT出力）は、Whisper系がネイティブ`[MM:SS]`解析、Qwen3ASREngineが同梱の`Qwen3ForcedAligner`と、エンジンごとに独立した別実装であり、共有アライナーは存在しない。Nemotronのオフラインバッチ推論は単一セグメントのみを返すため、`include_timestamps`を有効なまま使うとSRTが実質1行になり壊れた出力に見える。RNNTトークンタイムスタンプによるセグメント生成（案(a)）はPhase1で未検証かつPhase2のスコープを超えるため、**Nemotron選択時は`include_timestamps`チェックボックスを無効化し、その旨を表示する（案(b)）**方針とする。

実際のGPU実行・E2E動作確認・長尺音声実測（Phase2設計report§7のステップ5・6）は本指示書のスコープ外とし、本指示書完了後に別途、GPU使用直前の采連絡を伴う作業指示書を発行する。

## 3. ゴール（完了条件）

```bash
# 新規ファイルの存在確認
for f in core/nemotron_engine.py scripts/nemotron_infer.py scripts/setup_nemotron_venv.sh; do
  test -f "$f" && echo "OK_EXISTS_${f}" || echo "MISSING_${f}"
done

# 隔離venv構築スクリプトの構文チェック(GPU不要)
bash -n scripts/setup_nemotron_venv.sh && echo OK_SYNTAX_setup_script || echo FAIL_SYNTAX_setup_script

# webui.pyのoptionsリスト末尾追加・index=0不変の確認
python3 -c "
import ast
tree = ast.parse(open('webui.py').read())
# st.selectbox('モデル', options=[...], index=0) を探す
found = False
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'selectbox':
        for kw in node.keywords:
            if kw.arg == 'options' and isinstance(kw.value, ast.List):
                opts = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
                if 'nemotron' in str(opts[-1]).lower() and opts[0] == 'Qwen/Qwen3-ASR-1.7B':
                    found = True
print('OK_OPTIONS_APPEND_DEFAULT_UNCHANGED' if found else 'FAIL_OPTIONS_CHECK')
"

# 既存112件(111 passed, 1 skipped) + 新規回帰テストがすべてpassすること(GPU不要・モデルロード不要)
uv run python -m pytest tests -q 2>&1 | tail -5

# 生産用.venv/pyproject.toml/uv.lockが変更されていないことの機械確認
git diff --name-only -- .venv pyproject.toml uv.lock | wc -l | grep -qx 0 && echo OK_NO_ENV_CHANGE || echo FAIL_ENV_CHANGED
```

すべて`OK_*`/pytestが全件passし、`FAIL_*`/`MISSING_*`が一件もないこと。

## 4. 成果物の仕様・要件（Phase2設計report §1-7に準拠）

1. **`core/nemotron_engine.py`（新規）**: `NemotronSubprocessEngine(TranscriptionEngine)`。`transcribe()`/`get_engine_name()`を実装。設計report§1のサブプロセス起動・JSON1行パース・タイムアウト（`max(60, duration_sec*3+30)`秒）・異常終了時`RuntimeError`変換に従う。`is_nemotron_model(model_name)`静的関数も同モジュールに実装（`"nemotron" in name.lower()`、設計report§2）。
2. **`scripts/nemotron_infer.py`（新規）**: 隔離venv上で実行するサブプロセス側スクリプト。標準出力はJSON1行のみ（診断ログは`sys.stderr`へ）。設計report§1のPhase1実績パターンを踏襲。
3. **`scripts/setup_nemotron_venv.sh`（新規）**: 設計report§3のとおり。バージョン固定（`transformers==5.17.0`／`torch==2.14.0`）、冪等（既存ディレクトリがあれば何もせず終了）、生産用`.venv`非依存。
4. **`core/transcription_interface.py`の変更**: `UnifiedTranscriber.__init__`（L933-938実測）に`is_nemotron_model`判定を`is_qwen3_model`判定より前に挿入（設計report§2のコード案どおり）。
5. **`webui.py`の変更**:
   - L109-112の`selectbox` `options`末尾に`"nvidia/nemotron-3.5-asr-streaming-0.6b"`を追加、`index=0`は変更しない。
   - L119の`include_timestamps`チェックボックス: 選択中のモデルがNemotronの場合、`disabled=True`にし、"Nemotronは現時点でタイムスタンプ非対応です"等のキャプションを表示する（本指示書§2の追加決定事項）。
6. **回帰テスト（`tests/`、新規ファイルまたは既存への追加。GPU不要・モデルロード不要）**: 設計report§2の回帰テストケース1-5（既存3モデル名の解決不変・Nemotron新規解決・文字列排他性の網羅確認）を実装。いずれも`UnifiedTranscriber.__init__`直後のエンジンクラス判定のみを検証し、実際のモデルダウンロード・推論は発生させないこと。
7. **`core/nemotron_engine.py`のエラーハンドリング**: 設計report§6のとおり、隔離venv未構築時（`venv-nemotron-poc/bin/python`が存在しない）は明確なメッセージで`RuntimeError`を送出する。`webui.py`側の変更は不要（既存の`except BaseException`経路に乗るため）。

## 5. 作業範囲（スコープ）

**含む**:
- 上記4項目の成果物の実装
- 回帰テスト（既存モデル名の解決不変・Nemotron新規解決・デフォルト不変）の実装・実行
- 隔離venv未構築状態でのエラーメッセージ確認（GPU不要、`venv-nemotron-poc/bin/python`の存在チェックのみ）
- 構文チェック（`bash -n`）、既存の隔離venv（Phase1構築済み`venv-nemotron-poc/`）への`import`確認程度（CPU範囲）

**含まない**:
- GPU実行を伴う実際の推論・E2E動作確認（Phase2設計report§7ステップ5・6。別途、GPU使用直前の采連絡を伴う作業指示書を発行する）
- 長音声チャンク処理閾値（暫定300秒）のGPU実測による確定
- NeMo経路の実装（予備調査で依存解決の不確実性が判明済みのためスコープ外）
- 生産用`.venv/`・`pyproject.toml`・`uv.lock`への変更

## 6. 依存関係と提供資料

- 使用ブランチ: `feature/nemotron35-asr-phase1-investigation-20260926`（push済み、継続使用）
- 参照資料:
  - Phase2設計予備調査完了報告（`00_レビュー依頼/作から計への設計予備調査完了報告_Nemotron3.5ASR-StreamingPhase2_20260926.md`、commit 509e7ab）§1-7
  - Phase1実測結果報告（Nemotron推論スクリプトの実績パターン、`WORK_20260926_220529_phase1/nemotron_infer.py`）
- 実測項目（規則5、2026-09-26計実測）:
  - `webui.py` L109-112: モデル選択selectbox
  - `webui.py` L118-121: `include_timestamps`チェックボックス（`st.checkbox("タイムスタンプ付与(ForcedAligner使用、GPUメモリ約1.2GB追加)", value=False)`）
  - `core/transcription_interface.py` L400-: `Qwen3ASREngine`（`FORCED_ALIGNER_MODEL`等、L470-520台に実装閉じ）
  - `core/transcription_interface.py` L122-: `WhisperTranscriptionEngine`（`_parse_timestamped_text`等、ネイティブ`[MM:SS]`解析、L181実測）
  - `core/transcription_interface.py` L933-938: ディスパッチロジック（is_qwen3_model判定→else節Whisper）
  - `webui.py` L393-398: SRT出力（`item.settings.get("include_timestamps")`時のみ`segments_to_srt(result.segments)`呼び出し）
- 采条件7点（tc-ops #546、2026-09-26T13:34:49Z）、タイムスタンプ追加指摘（同T13:54:05Z）
- 遵守事項:
  - CLAUDE.md「.venv/ ディレクトリを削除・変更すべからず」「既存のクラス名やメソッド名を変更する際は影響範囲を調査すべし」
  - GPU使用を伴う作業は本指示書のスコープ外（別途作業指示書で対応）

## 7. 承認プロセス

- 計が本指示書を査（sa）へ査読依頼し、合格後に正式伝達する（本ファイルは査読依頼段階のドラフト）。査読合格時、采へ1行報告する（采指示の報告要件）。
- 実装完了後、計が受領し、査(sa)の品質検査を経て、計が最終承認する。
- 承認後、GPU実測（E2E動作確認・長尺音声実測）の作業指示書を計が別途起草する。着手直前に計経由で采へ連絡する（jev-local停止要否の確認のため、采条件⑥）。
