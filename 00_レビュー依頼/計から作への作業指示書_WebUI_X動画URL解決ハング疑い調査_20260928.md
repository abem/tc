# 計から作への作業指示書_WebUI_X動画URL解決ハング疑い調査_20260928

## 1. DoR (Definition of Ready) チェック

- [x] 1. 背景と目的が明確か
- [x] 2. ゴール（完了条件）が定義されているか（機械検査 exit 0 で判定可能か）
- [x] 3. スコープ（範囲）が限定されているか
- [x] 4. 成果物の仕様・要件が明確か
- [x] 5. 依存関係が解決されているか（原因候補箇所を計が実装確認済み、下記§6参照）
- [x] 6. 担当者と期限が設定されているか（担当: saku、期限: 特になし・通常優先度）
- [x] 7. レビュー/承認者が明確か（査読=査(sa)、最終承認=計(kei)）

## 2. 背景と目的

采(sai)からの方針指示（2026-09-28、agmsg ccc、原文要約、tc-ops #550）により起票。

tc-webUIでX(Twitter)動画URL（例: `https://x.com/callanxai/status/2103962270250291389/video/1`）を投入した際、キューが「解決中(ダウンロード等)」状態のまま進行が停止するようにユーザーが観測した。その後「処理中」へ進行したことも観測されており、**初期の停止が一時的ハングだったのか、単に正常な処理時間内だったのかは未特定**。再現性とタイムアウト設計の有無を確認し、必要なら是正すること。

## 3. ゴール（完了条件）

```bash
# 1. 再現性確認の結果（再現した/しなかった、条件、所要時間の実測値）が完了報告書に記載されていること
grep -q "再現性確認" <完了報告書パス> && echo OK_REPRO_SECTION_PRESENT

# 2. handlers/youtube.py の extract_video_info() / download_audio() のタイムアウト設計に関する
#    調査結果（現状timeout未設定であることの確認、導入要否の判断とその根拠）が完了報告書に
#    記載されていること
grep -q "タイムアウト" <完了報告書パス> && echo OK_TIMEOUT_SECTION_PRESENT

# 3. 是正を実施した場合、既存のYouTube URL経路（core/cli_workflow.py resolve_input_audio()の
#    "youtube"分岐）の挙動・既存テストが壊れていないこと
uv run python -m pytest tests -q 2>&1 | tail -5

# 4a. 生産用 pyproject.toml/uv.lock が変更されていないことの機械確認
#     (作業ツリーとHEADの単純比較ではsaku側でコミット済みの変更がHEADへ取り込まれた時点で
#     差分ゼロになり検知できない。分岐点=origin/devとの比較で判定する。査sa是正指摘)
git diff --name-only origin/dev...HEAD -- pyproject.toml uv.lock | wc -l | grep -qx 0 && echo OK_NO_LOCKFILE_CHANGE || echo FAIL_LOCKFILE_CHANGED

# 4b. 生産用 .venv/ が変更されていないことの機械確認
#     (.venv/は.gitignore対象のためgit diffでは検知不能。git以外の手段=ファイル一覧+サイズ+
#     更新日時のハッシュ比較で判定する。査sa是正指摘)
#     ベースライン(計が着手前2026-09-28に記録): bb9dafd582d867d5de3c5af2f60221f269e05124b77a197aeac9ecd1f672a38e
#     完了報告時、以下と同じコマンドを再実行しベースラインと一致することを確認・記載する
find .venv -type f -printf '%p %s %T@\n' 2>/dev/null | sort | sha256sum
```

## 4. 成果物の仕様・要件

**A. 再現性確認**:
- 報告されたURL（`https://x.com/callanxai/status/2103962270250291389/video/1`）、または同種のX動画URL（末尾に`/video/1`等のパス片が付くもの）で、`_resolve_input()`経路（`core/cli_workflow.py`の`resolve_input_audio()` → `handlers/youtube.py`の`YouTubeClient.download_audio()`）を実行し、「解決中」で長時間停止するかを確認する。
- 本番データでの実験は避け、再現用の類似URL・自分のテスト用アカウント等の投稿を使うこと（CLAUDE.md「本番データで実験すべからず」遵守）。

**B. タイムアウト設計の調査**:
- 計の予備調査で以下を実装確認済み（tc-ops #550記載、下記§6にも再掲）:
  - `handlers/youtube.py`の`extract_video_info()`（L61-80）: `subprocess.run(cmd, capture_output=True, text=True)`に**timeout未指定**。
  - `download_audio()`内の`subprocess.Popen`によるダウンロードループ（L133-148）も同様に**timeout未指定**。
- これらが「解決中」ハングの原因候補になり得るかを検証し、タイムアウト導入の要否を判断する。導入する場合は具体的な秒数設計（yt-dlp側の`--socket-timeout`等の活用も含め作の裁量）と、タイムアウト時のエラーハンドリング（`_resolve_input()`の`except Exception`経路で`job_queue.resolve_failed()`に正しく伝播するか）を確認・必要なら是正する。
- タイムアウトを導入しない判断をした場合も、その根拠（実測時間・yt-dlp側の挙動等）を完了報告書に明記すること。

**C. UI表示の確認**:
- ハング/長時間化した場合に、Web UI側の状態（「解決中」表示、ログ`item.log`への追記）がユーザーにとって分かりやすいか確認する。改善の要否は所見として報告すればよく、本指示書のスコープ内での実装は必須としない。

## 5. 作業範囲（スコープ）

**含む**:
- 上記A・B・Cの調査。Bで是正が必要と判断した場合の実装（`handlers/youtube.py`のtimeout導入等）。

**含まない**:
- X(Twitter)以外のURL種別（YouTube・Google Drive）の挙動変更。
- yt-dlp自体のバージョンアップ・依存関係変更（別途影響調査が必要なため、必要と判断した場合は完了報告書で提案のみとし、計・采の判断を仰ぐこと）。
- 生産用`.venv/`・`pyproject.toml`・`uv.lock`への変更。

## 6. 依存関係と提供資料

- 使用ブランチ: `feature/webui-x-video-resolve-hang-investigation-20260928`（dev最新から計が作成・push済み）
- 参照資料:
  - 采方針指示（agmsg ccc、2026-09-28T13:03:22Z/13:09:00Z/13:09:17Z、sai→kei、原文要約）
  - tc-ops #550（本件チケット）
- 実測項目（計実測、2026-09-28）:
  - `core/utils.py` L27-28・L40-45: `TWITTER_URL_PATTERNS`・`is_twitter_url()`（`re.match`による先頭一致のみで、末尾に`/video/1`等が付くURLも検出可能。検出漏れではない）
  - `core/cli_workflow.py` L46-63: `resolve_input_audio()`。`source_type in ("youtube", "twitter")`でtwitterもyoutubeと同じ`YouTubeClient.download_audio()`経路を使う
  - `handlers/youtube.py` L61-80: `extract_video_info()`。`subprocess.run()`にtimeout未指定
  - `handlers/youtube.py` L82-186: `download_audio()`。`subprocess.Popen`によるダウンロードループ（L140-148）もtimeout未指定
  - `webui.py` L228-262: `_start_resolution_job()`。入力解決はバックグラウンドスレッドで実行され、`_on_status()`経由で`item.log`に追記される（UI側の「解決中」表示の実体）
- 遵守事項:
  - CLAUDE.md「本番データで実験すべからず」
  - ブランチ戦略遵守（feature→dev→main）。mainはユーザーGOまで更新しない

## 7. 承認プロセス

- 計が本指示書を査（sa）へ査読依頼し、合格後に作（saku）へ正式伝達する。
- 完了後、計が受領し、査(sa)の品質検査を経て、計が最終承認する。
