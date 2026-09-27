# 査による運用手順書査読結果_WebUI本番worktree分離_20260927

> **発行日**: 2026年09月27日 / **発行者**: 査ロール（sa） / **対象**: tc-ops #548 C

## 判定: **合格**

## 検証内容（すべて査自身が実機で直接確認）

- `git worktree list`: `/home/abem/Projects/tc-prod` [dev] が実在、HEAD=89731a5でdev tipと一致
- `git diff dev -- pyproject.toml uv.lock`・`git diff dev -- config/`: いずれも空。①.venv共有・config.yaml不要の安全性根拠を確認
- 8個のシンボリックリンク（.venv/credentials.json/token.pickle/.env/config/context_hints.txt/output/logs/venv-nemotron）すべて実在し正しいリンク先を指すことを確認
- `config/context_hints.txt`が`.gitignore`の`*.txt`パターンで除外される（`git check-ignore -v`で確認）ため新worktreeに実体がなく、シンボリックリンクが必要という判断は正確
- 事前検証コマンド3件（import・streamlit --version・history.dbリンク）を査自身が再実行し、記載どおり成功することを確認
- **最重要**: 現在稼働中のプロセス（PID 438、稼働12時間半）の実際のcwd（`/proc/438/cwd`）が`/home/abem/Projects/tc`のままであり、コマンドラインにも`--server.fileWatcherType none`が含まれないことを確認した。**daemon-reload未実行につき現行稼働プロセスが無影響である」という記載は実機で正確に確認できた。**
- `--server.fileWatcherType`はStreamlit CLIの実在オプションであることを`streamlit run --help`で確認した（架空オプションではない）

## 参考情報（合否に影響しない）

切り戻し手順は「変更前」の内容を手動で戻す前提になっている。本文中の「変更前」コードブロックに内容自体は残っているため情報としては十分だが、緊急時に備え、切り戻し用のユニットファイル全文を別ファイルとして`/home/abem/`配下等に保存しておくと復旧が一段速くなる（必須ではない）。

## 計ロールへの報告

最終承認をお願いします。ユーザーへ渡すコマンドブロックは3点（①.venv共有②daemon-reload未実行の無影響③fileWatcherType実在確認）を査が実機で確認済みであり、安全に渡せると判断する。

**文書終了**
