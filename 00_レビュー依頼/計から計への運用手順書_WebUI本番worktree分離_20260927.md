# 運用手順書_WebUI本番worktree分離_20260927

**対象**: tc-ops #548 C（本番WebUIの運用分離）
**発行者**: 計(kei)
**査読依頼先**: 査(sa)

## 背景

采決定（2026-09-26T15:43:15Z、sai→kei）により、案1（別worktreeからの起動）+案2（`--server.fileWatcherType none`）を併用する。解決すべき5点（①.venv ②credentials等 ③output/history.db継続性 ④logs出力先 ⑤venv-nemotron参照先）を計が解決した上で、ユーザーへ「貼り付けて実行するだけのコマンド1ブロック（停止と起動）」を渡す。本番ブランチは`dev`。

## 実施内容（計が実施済み、ユーザー操作前の準備段階）

### 1. worktree作成

```bash
git worktree add /home/abem/Projects/tc-prod dev
```

現在のHEAD: `89731a5`（dev tip、`Merge feature/webui-history-phase3-search-export-20260910 into dev`）。

### 2. シンボリックリンクによる状態共有（①〜⑤の解決）

```bash
cd /home/abem/Projects/tc-prod
ln -s /home/abem/Projects/tc/.venv .venv                                    # ①
ln -s /home/abem/Projects/tc/credentials.json credentials.json              # ②
ln -s /home/abem/Projects/tc/token.pickle token.pickle                      # ②
ln -s /home/abem/Projects/tc/.env .env                                      # ②
ln -s /home/abem/Projects/tc/config/context_hints.txt config/context_hints.txt  # ②
ln -s /home/abem/Projects/tc/output output                                  # ③
ln -s /home/abem/Projects/tc/logs logs                                      # ④
ln -s /home/abem/Projects/tc/venv-nemotron venv-nemotron                    # ⑤
```

**①.venvの判断根拠**: `git diff origin/dev -- pyproject.toml uv.lock`が空（既に確認済み。tc-ops #546の全作業を通じてこの2ファイルは一度も変更していない）。よって依存関係は完全に同一であり、`.venv`（5.8GB）をシンボリックリンクで共有しても不整合が生じない。再構築（数分〜十分オーダーの重い処理）は不要と判断した。

**②credentials.json・token.pickle・.env・config/context_hints.txt**: いずれも`.gitignore`対象（機密情報・環境依存のため）で、`dev`をcheckoutしただけの新worktreeには存在しない。シンボリックリンクで実体を共有する（認証状態・APIトークンの二重管理を避ける）。なお`config/config.yaml`自体はGit管理下にあり、`dev`ブランチの内容と現行運用中の内容に差分がないことを確認済み（シンボリックリンク不要）。

**③output/**（2.0GB）: `output/history.db`を含む変換履歴ディレクトリ全体をシンボリックリンクし、新旧で履歴が分かれないようにした。

**④logs/**: シンボリックリンクにより、新worktree起動後もログは同一の場所（`/home/abem/Projects/tc/logs/`）に継続して書かれる。tc-ops #548 Bの是正（テストログの本番混入防止）が別途完了すれば、この共有ログは今後汚染されない。

**⑤venv-nemotron**: `dev`ブランチには現時点でNemotron関連コード（`core/nemotron_engine.py`等）が存在しない（tc-ops #546はfeatureブランチ上で未マージ）。したがって現時点ではこのシンボリックリンクは未使用（リンク先`/home/abem/Projects/tc/venv-nemotron/`もtc-ops #546フェーズBで構築予定、現時点では未構築）。将来tc-ops #546がdevへマージされた際、このシンボリックリンクにより追加作業なしで機能する設計とした。

### 3. systemdユニットファイルの変更

`/home/abem/.config/systemd/user/tc-webui.service`（Git非管理、ユーザーのホーム配下）を編集した。**編集のみで`daemon-reload`は未実行のため、現在稼働中のプロセスへの影響はない。**

変更前:
```ini
WorkingDirectory=/home/abem/Projects/tc
ExecStart=/home/abem/.local/bin/uv run streamlit run webui.py --server.headless true --server.port 8501
```

変更後:
```ini
WorkingDirectory=/home/abem/Projects/tc-prod
ExecStart=/home/abem/.local/bin/uv run streamlit run webui.py --server.headless true --server.port 8501 --server.fileWatcherType none
```

### 4. 事前検証（実施済み、破壊的操作なし）

```bash
cd /home/abem/Projects/tc-prod
uv run python -c "import core; from core.config import UnifiedConfig"  # → 正常動作確認
.venv/bin/streamlit --version  # → Streamlit 1.60.0(既存共有.venvから正常に実行できることを確認)
ls -la output/history.db  # → 実体（/home/abem/Projects/tc/output/history.db）へのリンクを確認
```

## ユーザーに渡すコマンド（未実行、査sa承認後に采経由で渡す）

同一systemdユニットの`daemon-reload`+`restart`で、停止と新worktreeでの起動が1操作で完結する。

```bash
systemctl --user daemon-reload
systemctl --user restart tc-webui.service
sleep 2
systemctl --user status tc-webui.service --no-pager
```

`status`出力で`Active: active (running)`・`Main PID`が新しいプロセスID・エラーが出ていないことを確認できれば成功。もし失敗した場合は、以下で切り戻せる（旧ユニット定義に戻すコマンドも合わせて用意）:

```bash
# 切り戻し(WorkingDirectory/ExecStartを元に戻してから実行)
# 1) /home/abem/.config/systemd/user/tc-webui.service を手動で元の内容に戻す
# 2) systemctl --user daemon-reload && systemctl --user restart tc-webui.service
```

## 査(sa)への確認依頼事項

1. worktree作成・シンボリックリンクの設計に問題がないか（特に①.venv共有の安全性根拠）。
2. systemdユニットファイルの変更内容が意図どおりか。
3. ユーザーへ渡すコマンドブロックが、停止と起動を過不足なく実現しているか。
4. 万一の切り戻し手順の妥当性。
