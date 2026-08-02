# (番号未採番・暫定発行): 検査報告書 - X(旧Twitter)動画URL取り込み対応

> **発行日**: 2026年08月02日 / **発行者**: 査ロール(sa) / **文書種別**: 検査報告書
> **検査対象**: `core/utils.py`・`core/cli_workflow.py`・`handlers/youtube.py`・`tests/test_core_utils.py`（ブランチ: `feature/x-twitter-url-support-2026-08-02`） / **宛先**: 計ロール(kei)
> **注記**: 前回同様、文書番号採番インフラ未整備のため番号なしの暫定発行とする(計承認済み)。

## 検査結果

### 判定: **合格**

## 1. 検査項目

| 確認項目 | 結果 | 備考 |
|---------|------|------|
| 対象ファイル一覧の一致 | ✅ | 4ファイル(core/utils.py・core/cli_workflow.py・handlers/youtube.py・tests/test_core_utils.py)、報告と完全一致 |
| 差分の数量(insertions/deletions) | ✅ | 査自身の`git diff --numstat`実測=57 insertions/8 deletions(4ファイル計)。報告値と完全一致(内訳: utils.py 15/1・cli_workflow.py 3/3・youtube.py 9/4・test_core_utils.py 30/0) |
| tc・core/config.py・core/transcription_interface.py無変更の確認 | ✅ | `git status`でいずれも変更なしを確認 |
| **計による是正事項の確認(最重点)** | ✅ | `git diff --stat -- config/config.yaml`を実行し差分0行を確認。計が検出・復元した内容が現状に正しく反映されている |
| 構文正当性 | ✅ | 対象4ファイルすべて`ast.parse`でOK |
| 単体テスト | ✅ | `uv run pytest -q` = 51 passed / 2 skipped / 0 failed（新規3件含め報告値と完全一致） |
| URL判定ロジックの設計一貫性 | ✅ | `is_twitter_url`が既存`is_youtube_url`と同一パターン(正規表現リスト+`re.match`ループ)で実装されており設計が一貫している |
| 実機再現(機能検証・X URL) | ✅ | 査自身が独立実行(§2.1)。作の報告と別のX動画を用いたが、検出→ダウンロード→文字起こし→一時ファイル削除→exit 0の一連の流れを確認 |
| 実機再現(ローカルファイル回帰確認) | ✅ | 査自身が独立実行(§2.2)。既存動作に変化なし |
| config.yaml経由の呼び出し等価性 | ✅ | `tc`内`input_source = args.input or config.get("gdrive", {}).get("url")`により、CLI引数経由とconfig.yaml経由は同一コード路に合流することをコード直読で確認。§2.1のCLI引数テストがconfig.yaml経路も等価に検証している(§5参照、config.yamlの再汚染リスクを避けるため意図的にconfig.yaml変更による再テストは行わなかった) |
| アップロード対応スコープ外の確認 | ✅ | `tc`の`if resolution.source_type in {"youtube", "gdrive"} and not args.no_upload:`が無変更のままであることを確認。"twitter"はこの集合に含まれないため、`--no-upload`指定の有無によらずアップロード処理へ進まない(意図的なスコープ外実装として妥当) |
| 削除済み/変更ロジックへの残存参照 | ✅ | `is_youtube_url`単独でのURL妥当性チェック(`download_audio`内)が`is_supported_url`へ置換されており、旧チェックへの依存が残っていないことを確認 |

## 2. 証拠: 実機再現ログ(査自身による独立実行)

### 2.1 X(Twitter) URLのエンドツーエンド再現

```
$ ./tc "https://x.com/hanakoxbt/status/2083602828744859845" --no-upload
...
Video title: Hanako | Head of Claude Code just dropped a free 35-...
Starting audio extraction: https://x.com/hanakoxbt/status/2083602828744859845
[download] 100% of 32.54MiB in 00:00:26 at 1.24MiB/s
...
Transcription completed: 32214 characters
文字起こし完了: output/20260802_110759_transcription.txt
Temporary file removed: output/Hanako-Head-of-Claude-Code-just-dropped-a-free-35-_2083598884362653696.wav
EXIT_CODE=0
```

作が使用した動画(375文字、生存確認済みの別動画)とは異なる動画を用いたため文字数は一致しないが、これは想定どおり(査は入力データではなく処理の正当性を独立に確認する立場のため、意図的に異なる実データを用いた)。X URL検出→ダウンロード→文字起こし→一時ファイル削除→exit 0の一連の流れそのものが正しく機能することを確認した。

### 2.2 ローカルファイル経路の回帰確認

```
$ ./tc samples/e2e_sample.wav --no-upload
...
文字起こし完了: 3文字
文字起こし結果（最初の500文字）:
はい。
```

既存のローカルファイル経路に変化がないことを確認した。

## 3. 単体テスト

```
$ uv run pytest -q
..................................ss.................                    [100%]
51 passed, 2 skipped in 1.29s
```

## 4. 合格判定前の3点自己反証

- **検証範囲**: 対象4ファイルすべての差分内容を読解し、URL判定・ワークフロー分岐・ハンドラー・テストの各層を確認した。「計による是正事項」(config.yaml復元)は査自身が`git diff --stat`で0行であることを直接確認しており、申告を鵜呑みにしていない
- **証拠**: 判定根拠はすべて査自身が直接実行したコマンド出力・直接読解したコード。差分数量も査自身の`git diff --numstat`実測に基づき、今回は報告値と完全一致することを確認した
- **判定**: 今回は合格判定に影響する不備・報告内容との不一致を検出しなかった。強いて記載すべき事項は§5のみ(手法上の判断の説明であり、不備ではない)。条件付き合格は用いていない

## 5. 補足(合格判定とは別レイヤー・不備ではなく手法の説明)

config.yamlのgdrive.url経由での動作(完了条件(4))について、査は意図的に**config.yamlを変更しての再テストを行わなかった**。理由: (a) `tc`のコード上、CLI引数とconfig.yaml値は`args.input or config.get(...)`で同一変数に合流し、以降のコード路は完全に同一であることをコード直読で確認済みであり、§2.1のCLI引数テストがconfig.yaml経路を実質的に等価検証している。(b) 本タスクにおいて計が既に一度、config.yaml復元漏れを検出・是正したばかりであり、査が同種の変更を追加で行うことは同じリスクを再現するだけで検証上の便益に乏しいと判断した。この判断について計・采から異論があれば、追加でconfig.yaml経由の再テストを実施する。

## 6. 計ロールへの報告

判定は合格。特記事項なし。最終承認をお願いする。

**文書終了**
