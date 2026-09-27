# 計から作への作業指示書_Nemotron分割最終手段化とGPU実測_20260927

## 1. DoR (Definition of Ready) チェック

- [x] 1. 背景と目的が明確か
- [x] 2. ゴール（完了条件）が定義されているか（機械検査 exit 0 で判定可能か）
- [x] 3. スコープ（範囲）が限定されているか
- [x] 4. 成果物の仕様・要件が明確か
- [x] 5. 依存関係が解決されているか（GPU使用許可済み、jev-local停止・自動再起動無効化済み）
- [x] 6. 担当者と期限が設定されているか（担当: saku、期限: 2026-09-28・最優先）
- [x] 7. レビュー/承認者が明確か（査読=査(sa)、最終承認=計(kei)）

**発行前の追加検証（正典: 06d_operations.md「5.1 検査健全性の原則」規則1・規則5／ADR-010）**

- [x] 8. 検査コマンド自身が結果に混入しないことを検証したか（規則1）: §3の判定はpytest結果・ファイル存在・grepの確認であり、検査コマンド自身が対象コードに混入することは構造上ない。
- [x] 9. 現況把握に必要な実測項目を網羅して提供したか（規則5）: 現行の`CHUNK_THRESHOLD_SEC`・`compute_chunk_boundaries()`の実装箇所を下記§6に列挙した。

## 2. 背景と目的

采方針指示（最優先、2026-09-26T17:58:49Z、sai→kei、ユーザー指示「とにかく改善、改悪はまずい」）により、tc-ops #546の均等分割方式は「末尾チャンクの欠落」を解消したが、新たな品質劣化を引き起こしたことが判明した。

**事象**: WebUI再起動後の変換履歴#78（994字）は、分割しない版#71（1007字）との類似度0.897。2つ目のチャンク（164-328秒）の範囲で誤認識が増加（語の消失・変化、末尾に無関係な語句が混入）。原因は分割により後半チャンクが前の文脈を失うこと。

**方針転換**: 分割は最後の手段とする。分割閾値（現在300秒固定）を、GPU実測に基づく安全な最大値へ引き上げ、通常想定される音声長（5〜30分程度）では原則として分割しない構成を目指す。

## 3. ゴール（完了条件）

```bash
# CHUNK_THRESHOLD_SECが実測に基づく値へ更新されていること(300から変更されていること)
grep -n "CHUNK_THRESHOLD_SEC = " core/nemotron_engine.py

# 無音区間への分割点寄せ機能が実装されていること(査sa指摘: 既存コメントに"無音"の語が
# 含まれ偽陽性となるため、固有の関数定義の存在で判定する。関数名は実装時に確定し、
# 本行のパターンを実際の関数名に置き換えて完了報告に記載すること。例:
# grep -q "^def find_silence_boundary\|^def _find_silence_boundary" core/nemotron_engine.py
grep -q "^def .*silence" core/nemotron_engine.py && echo OK_SILENCE_AWARE_SPLIT || echo MISSING_SILENCE_AWARE_SPLIT

# 回帰ゲート比較スクリプトが存在すること
test -f scripts/compare_nemotron_baseline.py && echo OK_COMPARE_SCRIPT_EXISTS || echo MISSING_COMPARE_SCRIPT

# 全pytestがpassすること
uv run python -m pytest tests -q 2>&1 | tail -5

# 生産用.venv/pyproject.toml/uv.lockが変更されていないことの機械確認
git diff --name-only -- .venv pyproject.toml uv.lock | wc -l | grep -qx 0 && echo OK_NO_ENV_CHANGE || echo FAIL_ENV_CHANGED
```

完了報告書には以下を含めること（機械検査は上記のみ。内容の妥当性はkeiが受領後に確認する）:

1. 5・10・15・20・30分（無分割）でのピークVRAM・処理時間の実測結果（表形式）
2. 決定した新しい`CHUNK_THRESHOLD_SEC`と、その根拠（実測データからどう安全マージン2GB以上を確保したか）
3. 分割点を無音区間へ寄せる機能の実装内容
4. 回帰ゲート比較スクリプトの仕様と使用方法
5. 基準音声（同一Driveファイル）での分割なし版（#71相当）との比較結果（一致または類似度0.98以上、末尾欠落なしの確認）

## 4. 成果物の仕様・要件

1. **GPU実測（5・10・15・20・30分、無分割）**: Nemotronを分割なしで各長さの音声にかけ、ピークVRAM（`nvidia-smi`）・処理時間を実測する。テスト音声は`output/`配下（本番パイプライン由来の可能性）を使わず、JSUT corpus（結合して各長さに調整、音声ファイル自体はGitコミット禁止・再配布不可ライセンス）またはテスト用YouTube音声等を用いること。
2. **`CHUNK_THRESHOLD_SEC`の更新**: 実測結果から、ピークVRAMが総量（実測時点の空き容量、jev-local停止中で約13GB）から2GB以上の余裕を残せる最大音声長を求め、安全側に倅め、新しい閾値として`core/nemotron_engine.py`の`CHUNK_THRESHOLD_SEC`定数を更新する。
3. **分割点の無音区間への寄せ**: 新閾値を超える音声（分割が必要な場合）について、`compute_chunk_boundaries()`または分割実行箇所に、無音区間検出（例: `librosa.effects.split`等）により分割点を発話の切れ目へ調整する機能を追加する。無音区間が見つからない場合は、既存の均等分割（時刻ベース）へフォールバックすること。
4. **回帰ゲート比較スクリプト（`scripts/compare_nemotron_baseline.py`、新規）**: 基準音声（同一Driveファイル、下記§6の取り扱い条件に従う）に対し、Nemotronの分割なし実行結果（基準）と、現在の実装（閾値・分割ロジック適用後）での実行結果を比較し、(a)完全一致、または(b)類似度0.98以上かつ末尾欠落なし、のいずれかを満たすかを判定して終了コードで結果を返すスクリプトを作成する。**類似度の算出方法を明記すること**: `difflib.SequenceMatcher`は`autojunk=False`を明示指定すること（査sa実測: 同一の2テキストで`autojunk`既定値(True)では0.824、`autojunk=False`では0.897(0.896551724137931)となり、日本語文の比較で約7ポイントの差が生じることを確認済み。既定値のままでは背景記載の類似度0.897と一致しない）。スクリプトのdocstringおよび完了報告書に算出方法（`autojunk=False`である旨）を明記すること。査(sa)が今後のNemotron変更の検査時にこのスクリプトを実行できるようにすること（使用方法を完了報告書に明記）。
5. **本作業自体の回帰確認**: 上記4のスクリプトを実際に実行し、現在の実装（新閾値・無音区間寄せ実装後）が基準音声で合格することを確認する。

## 5. 作業範囲（スコープ）

**含む**:
- 上記1-5の実測・実装・スクリプト作成・確認（GPU使用を含む）
- `core/nemotron_engine.py`の`CHUNK_THRESHOLD_SEC`・分割ロジックの変更

**含まない**:
- 生産用`.venv/`・`pyproject.toml`・`uv.lock`への変更
- Qwen3ASREngineへの同様の変更（tc-ops #547で別途検討中、本指示書のスコープ外）
- 本番のGoogle Driveフォルダ・WebUI/CLIのフル実行経路の使用（采条件、Driveへの自動アップロード回避のため）

## 6. 依存関係と提供資料

- 使用ブランチ: `feature/nemotron35-asr-phase1-investigation-20260926`（継続使用）
- 参照資料:
  - 采方針指示（agmsg ccc、2026-09-26T17:58:49Z、sai→kei、原文）
  - 基準音声: Google Drive `https://drive.google.com/file/d/1sUff4Af40_ZaFqb6L4XkG--5Loz1XNWO/view`（変換履歴#71・#75-78で使用した同一ファイル）
    - **取り扱い条件（遵守必須、既存の采指示を継続適用）**: ①ダウンロードのみ、WebUI/CLIのフル実行経路（Driveへの自動アップロードを伴う）は使わない ②ダウンロードしたファイルは作業後に削除する ③GPU使用中はWebUIでのユーザー変換と計測を重ねないこと（ログ・GPU使用量で確認する、采指示）
- 実測項目（規則5、2026-09-27計実測、対象=現行ブランチtip、commit f85d1b7）:
  - `core/nemotron_engine.py` L64: `CHUNK_THRESHOLD_SEC = 300`
  - `core/nemotron_engine.py` L78-: `compute_chunk_boundaries(duration_sec, chunk_threshold_sec=CHUNK_THRESHOLD_SEC)`（均等分割方式、tc-ops #546是正で確立済み）
- 遵守事項:
  - CLAUDE.md「.venv/ ディレクトリを削除・変更すべからず」「本番データで実験すべからず」
  - GPU使用は許可済み（ユーザーがjev-local停止・自動再起動無効化済み、2026-09-26T17:58:49Z采指示）。着手前の追加連絡は不要。
  - WebUIでのユーザー変換とGPU計測を重ねないこと

## 7. 承認プロセス

- 計が本指示書を査（sa）へ査読依頼し、合格後に正式伝達する（本ファイルは査読依頼段階のドラフト、最優先対応のため迅速に進める）。
- 完了後、計が受領し、査(sa)の品質検査（回帰ゲート比較スクリプトの実行を含む）を経て、計が最終承認する。
- 承認後、「WebUI再起動で確認可」を采へ1行報告する（采指示の報告要件。ユーザー確認基準: 同一ファイルで分割なし版#71と同等の文字数・内容になること）。
