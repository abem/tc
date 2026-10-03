"""scripts/release_dev_main.sh(dev → main 統合・push・WebUI 再起動)の挙動テスト。

一時ディレクトリに「origin(bare)」と「本番に見立てたクローン(prod)」を作り、スクリプトを実際に動かす。
本物の tc-prod・GitHub・systemd には一切触れない(環境変数 TC_PROD / TC_SYSTEMCTL / TC_LOG / TC_PORT で差し替える)。

守る性質(独立レビューで見つかった事故経路):
- 前提が崩れていれば、何も変更せずに止まる(fetch して origin の最新と比べる)
- 本番 dev の更新は、origin への push が成功した後に行う(push が拒否されたとき、本番だけ進んだ状態にしない)
- WebUI のジョブ(ダウンロード中を含む)を、ログとプロセスから判断し、あれば再起動しない
"""

import http.server
import os
import subprocess
import threading
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_dev_main.sh"


def git(cwd, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check
    ).stdout.strip()


@pytest.fixture
def sandbox(tmp_path):
    origin = tmp_path / "origin.git"
    prod = tmp_path / "prod"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(prod)], check=True)
    git(prod, "config", "user.email", "t@example.com")
    git(prod, "config", "user.name", "tester")
    git(prod, "config", "commit.gpgsign", "false")
    git(prod, "remote", "add", "origin", str(origin))
    (prod / "a.txt").write_text("base\n")
    git(prod, "add", ".")
    git(prod, "commit", "-q", "-m", "base")
    git(prod, "branch", "dev")
    git(prod, "push", "-q", "origin", "main", "dev")
    git(prod, "fetch", "-q", "origin")
    git(prod, "switch", "-q", "dev")
    git(prod, "branch", "--set-upstream-to=origin/dev", "dev")
    # 機能ブランチ(dev から 1 コミット先行)
    git(prod, "switch", "-q", "-c", "feature")
    (prod / "b.txt").write_text("feature\n")
    git(prod, "add", ".")
    git(prod, "commit", "-q", "-m", "feature work")
    git(prod, "switch", "-q", "dev")

    log = tmp_path / "transcription.log"
    log.write_text("")
    fake_systemctl = tmp_path / "fake-systemctl"
    fake_systemctl.write_text(
        "#!/bin/bash\n"
        'echo "$@" >> "$FAKE_SYSTEMCTL_LOG"\n'
        'case "$*" in\n'
        '  *is-active*) echo active ;;\n'
        '  *MainPID*) echo 0 ;;\n'
        '  *ActiveEnterTimestamp*) echo "Thu 1970-01-01 00:00:00 UTC" ;;\n'
        "esac\n"
    )
    fake_systemctl.chmod(0o755)
    return SimpleSandbox(tmp_path, origin, prod, log, fake_systemctl)


class SimpleSandbox:
    def __init__(self, root, origin, prod, log, systemctl):
        self.root, self.origin, self.prod, self.log, self.systemctl = root, origin, prod, log, systemctl
        self.systemctl_log = root / "systemctl.calls"

    def env(self, **extra):
        env = dict(os.environ)
        env.update(
            TC_PROD=str(self.prod),
            TC_LOG=str(self.log),
            TC_SYSTEMCTL=str(self.systemctl),
            FAKE_SYSTEMCTL_LOG=str(self.systemctl_log),
            TC_SERVICE="fake.service",
            TC_PORT="1",  # 既定では到達しない(ヘルスチェックを使うテストだけ上書きする)
        )
        env.update(extra)
        return env

    def run(self, *args, **env_extra):
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True, text=True, env=self.env(**env_extra), timeout=120,
        )

    def refs(self):
        return {
            "prod_dev": git(self.prod, "rev-parse", "dev"),
            "prod_main": git(self.prod, "rev-parse", "main"),
            "origin_dev": git(self.origin, "rev-parse", "dev"),
            "origin_main": git(self.origin, "rev-parse", "main"),
        }


@pytest.fixture
def health_server():
    """ヘルスチェック(/_stcore/health)に 200 を返す小さな HTTP サーバー。"""

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


class TestSuccess:
    def test_integrates_dev_and_main_and_restarts(self, sandbox, health_server):
        feature = git(sandbox.prod, "rev-parse", "feature")

        r = sandbox.run("feature", "Merge dev into main (test)", TC_PORT=str(health_server))

        assert r.returncode == 0, r.stdout + r.stderr
        refs = sandbox.refs()
        assert refs["prod_dev"] == refs["origin_dev"] == feature
        assert refs["prod_main"] == refs["origin_main"]
        main = refs["origin_main"]
        assert len(git(sandbox.origin, "rev-list", "--parents", "-n", "1", main).split()) == 3  # マージコミット
        assert git(sandbox.origin, "rev-parse", f"{main}^{{tree}}") == git(sandbox.origin, "rev-parse", f"{feature}^{{tree}}")
        assert "Merge dev into main (test)" in git(sandbox.origin, "log", "-1", "--format=%s", main)
        assert "restart" in sandbox.systemctl_log.read_text()
        assert "main-merge" not in git(sandbox.prod, "worktree", "list")  # 一時 worktree を残さない

    def test_no_restart_flag_skips_restart(self, sandbox):
        r = sandbox.run("--no-restart", "feature", "msg")

        assert r.returncode == 0, r.stdout + r.stderr
        assert not sandbox.systemctl_log.exists() or "restart" not in sandbox.systemctl_log.read_text()
        refs = sandbox.refs()
        assert refs["prod_dev"] == refs["origin_dev"] == git(sandbox.prod, "rev-parse", "feature")

    def test_second_run_with_the_next_feature_works_after_main_has_merge_commits(self, sandbox):
        """main には dev に無いマージコミットが積まれる。それでも次の統合が前提チェックを通る。"""
        assert sandbox.run("--no-restart", "feature", "first").returncode == 0
        git(sandbox.prod, "switch", "-q", "-c", "feature2")
        (sandbox.prod / "c.txt").write_text("again\n")
        git(sandbox.prod, "add", ".")
        git(sandbox.prod, "commit", "-q", "-m", "second")
        git(sandbox.prod, "switch", "-q", "dev")

        r = sandbox.run("--no-restart", "feature2", "second")

        assert r.returncode == 0, r.stdout + r.stderr
        assert sandbox.refs()["origin_dev"] == git(sandbox.prod, "rev-parse", "feature2")


class TestDryRun:
    def test_dry_run_changes_nothing(self, sandbox):
        before = sandbox.refs()

        r = sandbox.run("--dry-run", "feature")

        assert r.returncode == 0, r.stdout + r.stderr
        assert sandbox.refs() == before
        assert "何も変更していません" in r.stdout


class TestPreconditions:
    """前提が崩れているときは、何も変更せずに止まる(ローカルも origin も)。"""

    def _assert_unchanged(self, sandbox, before, result):
        assert result.returncode != 0
        assert sandbox.refs() == before
        assert "中止" in result.stderr

    def test_origin_dev_advanced_is_detected_by_fetch(self, sandbox):
        """origin が先に進んでいる(別の人が dev を更新した)。fetch していないと、古い参照のまま前提を通り、
        本番 dev を進めてから push が拒否される。"""
        other = sandbox.root / "other"
        subprocess.run(["git", "clone", "-q", str(sandbox.origin), str(other)], check=True)
        git(other, "config", "user.email", "o@example.com")
        git(other, "config", "user.name", "other")
        git(other, "switch", "-q", "dev")
        (other / "z.txt").write_text("someone else\n")
        git(other, "add", ".")
        git(other, "commit", "-q", "-m", "someone else")
        git(other, "push", "-q", "origin", "dev")
        before = sandbox.refs()

        r = sandbox.run("--no-restart", "feature", "msg")

        self._assert_unchanged(sandbox, {**before, "origin_dev": git(sandbox.origin, "rev-parse", "dev")}, r)
        assert git(sandbox.prod, "rev-parse", "dev") == before["prod_dev"]  # 本番 dev は動かない
        # push が拒否される前に、前提チェックの段階で(fetch して)分かること
        assert "origin/dev と一致しません" in r.stderr
        assert "push" not in r.stdout.lower().replace("origin を fetch", "")

    def test_dirty_prod_working_tree(self, sandbox):
        (sandbox.prod / "a.txt").write_text("edited in prod\n")
        before = sandbox.refs()

        r = sandbox.run("--no-restart", "feature", "msg")

        self._assert_unchanged(sandbox, before, r)

    def test_main_and_dev_trees_differ(self, sandbox):
        git(sandbox.prod, "switch", "-q", "main")
        (sandbox.prod / "only-main.txt").write_text("x\n")
        git(sandbox.prod, "add", ".")
        git(sandbox.prod, "commit", "-q", "-m", "main only")
        git(sandbox.prod, "push", "-q", "origin", "main")
        git(sandbox.prod, "switch", "-q", "dev")
        before = sandbox.refs()

        r = sandbox.run("--no-restart", "feature", "msg")

        self._assert_unchanged(sandbox, before, r)
        assert "内容(tree)が一致しません" in r.stderr and "dev と main" in r.stderr  # 前提チェックで止まる

    def test_feature_not_descended_from_dev(self, sandbox):
        git(sandbox.prod, "switch", "-q", "dev")
        (sandbox.prod / "d.txt").write_text("dev moved\n")
        git(sandbox.prod, "add", ".")
        git(sandbox.prod, "commit", "-q", "-m", "dev moved")
        git(sandbox.prod, "push", "-q", "origin", "dev")
        git(sandbox.prod, "switch", "-q", "main")
        git(sandbox.prod, "merge", "-q", "--no-ff", "dev", "-m", "sync main")
        git(sandbox.prod, "push", "-q", "origin", "main")
        git(sandbox.prod, "switch", "-q", "dev")
        before = sandbox.refs()

        r = sandbox.run("--no-restart", "feature", "msg")  # feature は古い dev から分岐

        self._assert_unchanged(sandbox, before, r)

    def test_unknown_branch_and_unknown_flag(self, sandbox):
        before = sandbox.refs()

        assert sandbox.run("--no-restart", "nope", "msg").returncode != 0
        assert sandbox.run("--bogus", "feature", "msg").returncode != 0
        assert sandbox.refs() == before

    def test_main_checked_out_in_another_worktree(self, sandbox):
        wt = sandbox.root / "wt-main"
        git(sandbox.prod, "worktree", "add", "-q", str(wt), "main")
        before = sandbox.refs()

        r = sandbox.run("--no-restart", "feature", "msg")

        self._assert_unchanged(sandbox, before, r)

    def test_missing_message_is_rejected(self, sandbox):
        before = sandbox.refs()

        r = sandbox.run("--no-restart", "feature")

        assert r.returncode != 0
        assert sandbox.refs() == before


class TestPushRejected:
    def test_local_prod_is_not_advanced_when_push_is_rejected(self, sandbox):
        """origin が push を拒否した(競合・権限など)。本番 dev・main は動かさない(旧版は本番 dev が先に進んでいた)。"""
        hook = sandbox.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/bash\necho 'rejected by test' >&2\nexit 1\n")
        hook.chmod(0o755)
        before = sandbox.refs()

        r = sandbox.run("--no-restart", "feature", "msg")

        assert r.returncode != 0
        assert sandbox.refs() == before
        assert "変更していません" in (r.stdout + r.stderr)
        assert "main-merge" not in git(sandbox.prod, "worktree", "list")

    def test_push_is_atomic_for_dev_and_main(self, sandbox):
        """dev と main は一緒に更新される(片方だけ進まない)。update フックは ref ごとに判定され、
        main への更新だけを拒否する。--atomic でなければ dev だけが origin で進んでしまう。"""
        hook = sandbox.origin / "hooks" / "update"
        hook.write_text(
            "#!/bin/bash\n"
            'if [ "$1" = "refs/heads/main" ]; then echo "main rejected" >&2; exit 1; fi\n'
            "exit 0\n"
        )
        hook.chmod(0o755)
        before = sandbox.refs()

        r = sandbox.run("--no-restart", "feature", "msg")

        assert r.returncode != 0
        assert sandbox.refs() == before  # origin の dev も動いていない


class TestBusyDetection:
    def _log(self, sandbox, *lines):
        sandbox.log.write_text("\n".join(lines) + "\n")

    def test_resolving_item_blocks_restart_even_when_queue_count_is_zero(self, sandbox):
        """ダウンロード中(RESOLVING)の項目は、dispatch_next の行(queued_count=0)には現れない。
        旧版はログ最終行の dispatch_next だけで判断し、空と誤判定して再起動でダウンロードを殺していた。"""
        self._log(
            sandbox,
            "2026-10-03 03:51:15,889 - core.webui_workflow - INFO - 状態遷移 item_id=1 (新規)->RESOLVING label=x",
            "2026-10-03 03:51:16,983 - core.webui_workflow - INFO - dispatch_next呼び出し current_item_id=None queued_count=0",
        )
        before = sandbox.refs()

        r = sandbox.run("feature", "msg")

        assert r.returncode != 0
        assert sandbox.refs() == before  # 何も変更されない
        assert "RESOLVING" in (r.stdout + r.stderr)

    def test_processing_item_blocks_restart(self, sandbox):
        self._log(
            sandbox,
            "2026-10-03 03:58:32,494 - core.webui_workflow - INFO - 状態遷移 item_id=3 QUEUED->PROCESSING label=y",
        )

        r = sandbox.run("feature", "msg")

        assert r.returncode != 0
        assert "PROCESSING" in (r.stdout + r.stderr)

    def test_finished_items_do_not_block(self, sandbox, health_server):
        self._log(
            sandbox,
            "2026-10-03 03:51:15,889 - core.webui_workflow - INFO - 状態遷移 item_id=1 (新規)->RESOLVING label=x",
            "2026-10-03 04:11:37,428 - core.webui_workflow - INFO - 状態遷移 item_id=1 PROCESSING->DONE output_file=o",
            "2026-10-03 04:20:00,000 - core.webui_workflow - INFO - 状態遷移 item_id=2 (新規)->RESOLVING label=z",
            "2026-10-03 04:20:30,000 - core.webui_workflow - INFO - 状態遷移 item_id=2 RESOLVING->FAILED error=e",
        )

        r = sandbox.run("feature", "msg", TC_PORT=str(health_server))

        assert r.returncode == 0, r.stdout + r.stderr

    def test_missing_log_is_treated_as_unknown_and_blocks_restart(self, sandbox):
        """ログが無い=状態が分からない。黙って「空」と見なさない。"""
        sandbox.log.unlink()

        r = sandbox.run("feature", "msg")

        assert r.returncode != 0
        assert "確認できません" in (r.stdout + r.stderr)

    def test_busy_does_not_block_when_restart_is_skipped(self, sandbox):
        self._log(
            sandbox,
            "2026-10-03 03:51:15,889 - core.webui_workflow - INFO - 状態遷移 item_id=1 (新規)->RESOLVING label=x",
        )

        r = sandbox.run("--no-restart", "feature", "msg")

        assert r.returncode == 0, r.stdout + r.stderr

    def test_force_restart_overrides(self, sandbox, health_server):
        self._log(
            sandbox,
            "2026-10-03 03:51:15,889 - core.webui_workflow - INFO - 状態遷移 item_id=1 (新規)->RESOLVING label=x",
        )

        r = sandbox.run("--force-restart", "feature", "msg", TC_PORT=str(health_server))

        assert r.returncode == 0, r.stdout + r.stderr

    def test_running_downloader_process_blocks_restart(self, sandbox):
        """ログに現れなくても、WebUI 配下で yt-dlp / ffmpeg が動いていれば実行中とみなす。"""
        fake_pid_holder = sandbox.root / "child.sh"
        fake_pid_holder.write_text("#!/bin/bash\nsleep 30\n")
        fake_pid_holder.chmod(0o755)
        # 親(WebUI 本体の代役)が yt-dlp という名前の子を持つ
        parent = subprocess.Popen(
            ["bash", "-c", "exec -a streamlit-fake bash -c 'exec -a yt-dlp sleep 30 & wait'"]
        )
        try:
            import time

            time.sleep(0.5)
            fake = sandbox.root / "fake-systemctl-pid"
            fake.write_text(
                "#!/bin/bash\n"
                'case "$*" in\n'
                "  *is-active*) echo active ;;\n"
                f"  *MainPID*) echo {parent.pid} ;;\n"
                '  *ActiveEnterTimestamp*) echo "Thu 1970-01-01 00:00:00 UTC" ;;\n'
                "esac\n"
            )
            fake.chmod(0o755)

            r = sandbox.run("feature", "msg", TC_SYSTEMCTL=str(fake))

            assert r.returncode != 0
            assert "yt-dlp" in (r.stdout + r.stderr)
        finally:
            subprocess.run(["pkill", "-P", str(parent.pid)])
            parent.kill()
