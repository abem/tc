# 査から計への検査報告書 - Nemotron3.5ASR-StreamingPhase1予備調査完了報告(saku)

> **発行日**: 2026年09月26日 / **発行者**: 査ロール（sa） / **文書種別**: 検査報告書
> **検査対象**: `00_レビュー依頼/作から計への予備調査完了報告_Nemotron3.5ASR-StreamingPhase1_20260926.md` / **宛先**: 計ロール

## 検査結果

### 判定: **合格**

## 1. セルフチェック証跡の確認（最優先・プロセス2）

7項目チェックリストが全て記載され、署名（saku）・日付（2026年09月26日）による完了宣言あり。項目7は「スクリプトではないため該当なし」と明記されており、対象外理由も妥当。→ 品質検査へ進行。

## 2. 完了条件（作業指示書§3）の機械検証

査が独立に実行（一次データ。作・計の自己申告は使わない）:

```
$ test -f "$REPORT" && echo OK_EXISTS
OK_EXISTS
$ for pat in transformers衝突可否 隔離実行案 VRAM要件 テスト音声選定 Phase1実行計画; grep -q "^#.*${pat}" "$REPORT" ...
OK_SECTION_transformers衝突可否
OK_SECTION_隔離実行案
OK_SECTION_VRAM要件
OK_SECTION_テスト音声選定
OK_SECTION_Phase1実行計画
$ git diff --name-only -- .venv pyproject.toml uv.lock | wc -l | grep -qx 0 && echo OK_NO_ENV_CHANGE
OK_NO_ENV_CHANGE
$ git status --porcelain -- .venv pyproject.toml uv.lock
(出力なし)
```

計の独立確認結果と一致。全項目 exit 0 相当（OK）。

## 3. 内容の証拠ベース検証（原則2。一次資料への直接アクセスで確認）

| 章 | 検証項目 | 検証手段 | 結果 |
|---|---|---|---|
| §1 | transformers>=5.13.0要件の明記 | HuggingFaceモデルカード（`nvidia/nemotron-3.5-asr-streaming-0.6b`）をWebFetchで直接確認 | 一致（"available in 🤗 Transformers starting from v5.13.0"） |
| §1 | VRAM明示値なし | 同モデルカード確認 | 一致（数値記載なし） |
| §1 | 現行.venv実測（transformers==4.57.6・qwen-asr<5） | `uv.lock` L3002-3019・`pyproject.toml` L19/L37-41を実ファイルでsed確認 | 一致 |
| §1 | nemo-toolkit最新3.0.0・Python3.12+・PyTorch2.7+ | PyPI (`nemo-toolkit`) をWebFetchで直接確認 | 一致 |
| §1 | backchannel#36のtransformers 4.12.2巻き戻し記述 | GitHub PRをWebFetchで直接確認 | 一致（原文引用も一致） |
| §1 | NeMo issue #14505のタイトル | GitHubをWebFetchで直接確認 | 一致 |
| §1 | transformers公式docsにNemotron3_5AsrForRNNT/Processor実在 | 公式docsページをWebFetchで直接確認 | 一致（クラス定義あり） |
| §2 | `.gitignore` L62=`venv*/`・L65=`.venv/` | 実ファイルでsed確認 | 一致 |
| §2 | `core/transcription_interface.py`のクラス構成（L73-121抽象/L122-Whisper/L400-Qwen3、transcribe()/get_engine_name()の2メソッド） | `grep -n "^class \|def transcribe\|def get_engine_name"` で実測 | 一致（境界行まで完全一致） |
| §3 | 実機GPU・VRAM（RTX 4080 SUPER・総量16376MiB） | `nvidia-smi`実行 | 一致（空き容量は経時変化のため厳密値は再実測=2874MiB、報告時点2825MiBと近似） |
| §2 | ディスク空き容量(720GB) | `df -h /`実行 | 一致（236G/1007G使用、720G空き） |
| §4 | `docs/user-guides/configuration.md` L41のURL | sed確認 | 一致 |
| §4 | 該当YouTube動画のタイトル | WebFetchで直接確認 | 一致（「【検証】電動キックボード...」） |
| §4 | `config/config.yaml` L4が別のGDriveリンクである（生産デフォルトと非同一） | 実ファイル確認 | 一致 |
| §4 | JSUTコーパス（10時間・女性話者・日本語・再配布不可・ライセンス条件） | 一次配布元をWebFetchで直接確認 | 一致（原文引用も一致） |
| §4 | 査の改善推奨（output/除外）の反映 | 本文§4「査sa指摘により除外」の記載を確認 | 反映済み（commit 1b12e49のメッセージにも同旨明記） |
| 全体 | 参照コミット1b12e49の実在・内容 | `git show 1b12e49` | 実在。査読合格・改善推奨反映の記述と一致 |

査読不能・未検証のまま残した項目はない。動画の秒数(1664秒)自体は独立ダウンロードでの再実測はしていないが、タイトル一致により対象動画の同一性は確認済みであり、測定手法（yt-dlp）自体は健全なため、この一点は「未検証」ではなく「秒数の桁レベル再確認は行っていない」と明記する。

## 4. 完了報告書の形式確認

`01_ロール定義/templates/完了報告テンプレート.md`が定める6要素（作業内容の要約／成果物一覧／自己評価／セルフチェック結果7項目／完了宣言／次のステップ）は、見出し文言としては一部（成果物一覧・自己評価・次のステップ）が明示ラベルを持たないが、内容としては以下の形で実質的にすべて充足している:
- 成果物一覧 → 「Git管理依頼」節が対象ファイルのフルパスを明記
- 自己評価 → §3のVRAM異常値を隠さず「原因未特定」と正直に記載する形で内在
- 次のステップ → 「未解決事項（計への確認事項）」節＋「WBS更新依頼」節

要件非該当（内容充足・見出し文言のみの差異）と判断し、判定には影響させない（改善推奨として下記に記載）。

## 5. 合格判定前の3点自己反証

1. **検証範囲**: 5項目すべての主要事実（外部一次資料7件・リポジトリ内実測9件）を査自身が個別に実行・WebFetchで確認した。一部（既存テスト資産の網羅性）は前段の作業指示書査読時に査自身が`find`で先行検証済み。
2. **証拠**: 判定根拠はすべて査自身が直接取得した一次データ（git/sed/grep/nvidia-smi/df の実行結果、HuggingFace・PyPI・GitHubの直接WebFetch結果）であり、作・計の自己申告をそのまま採用した箇所はない。
3. **判定**: 検出した項目は2件（形式のラベル差異・VRAM異常値）で、いずれも要件非該当または作自身が既に正直に開示済みの事実であり、二値評価の要件（不合格基準）には該当しない。条件付き合格は出していない。

## 6. 改善推奨（合否外・別レイヤー）

1. 完了報告書の見出しラベルを`01_ロール定義/templates/完了報告テンプレート.md`の文言（成果物一覧／自己評価／次のステップ／証拠ベース原則4項目のブロック）に合わせると、以後の形式監査が機械的に行いやすくなる。
2. §3で報告されたVRAM異常（空き2825MiB時点で13221MiB使用中だが該当プロセスが`nvidia-smi --query-compute-apps`で検出できない）は、Phase1実測のVRAM実測値の再現性・比較公平性に影響しうる。Phase1着手前に原因特定（WSL2の表示制約か、他プロセスの残留か）を計の判断で追加調査するか、少なくともPhase1実行計画に「着手直前の再実測」を明記の上で進めることを推奨する（saku自身も§5でこの点を認識済み）。

## 7. 計ロールへの報告

最終承認・WBS更新をお願いします。

**文書終了**
