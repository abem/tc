"""アップロード領域(output/uploads)の古いファイルの整理(tc-ops #578)。"""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.uploads import cleanup_old_uploads

DAY = 86400


def _age(path: Path, days: float) -> None:
    t = time.time() - days * DAY
    os.utime(path, (t, t))


def _make_upload(area: Path, sub: str, name: str = "a.wav", age_days: float = 0) -> Path:
    d = area / sub
    d.mkdir(parents=True)
    f = d / name
    f.write_bytes(b"x")
    _age(d, age_days)
    return d


class TestCleanupOldUploads:
    def test_removes_old_upload_dirs_and_keeps_recent_ones(self, tmp_path):
        old = _make_upload(tmp_path, "old", age_days=10)
        recent = _make_upload(tmp_path, "recent", age_days=1)

        removed = cleanup_old_uploads(tmp_path, max_age_days=7)

        assert removed == ["old"]
        assert not old.exists()
        assert (recent / "a.wav").exists()

    def test_boundary_just_under_the_limit_is_kept(self, tmp_path):
        kept = _make_upload(tmp_path, "kept", age_days=6.9)

        assert cleanup_old_uploads(tmp_path, max_age_days=7) == []
        assert kept.exists()

    def test_removes_old_legacy_flat_files_from_before_per_upload_dirs(self, tmp_path):
        legacy = tmp_path / "meeting.wav"
        legacy.write_bytes(b"x")
        _age(legacy, 30)
        fresh = tmp_path / "fresh.wav"
        fresh.write_bytes(b"x")

        removed = cleanup_old_uploads(tmp_path, max_age_days=7)

        assert removed == ["meeting.wav"]
        assert not legacy.exists() and fresh.exists()

    def test_protected_path_is_kept_even_when_old(self, tmp_path):
        busy = _make_upload(tmp_path, "busy", age_days=30)
        idle = _make_upload(tmp_path, "idle", age_days=30)

        removed = cleanup_old_uploads(tmp_path, max_age_days=7, protected_paths=[busy / "a.wav"])

        assert removed == ["idle"]
        assert busy.exists() and not idle.exists()

    def test_symlinks_are_never_followed_or_removed(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "precious.txt").write_text("keep")
        area = tmp_path / "area"
        area.mkdir()
        link = area / "link"
        link.symlink_to(outside, target_is_directory=True)
        os.utime(link, (time.time() - 30 * DAY,) * 2, follow_symlinks=False)

        removed = cleanup_old_uploads(area, max_age_days=7)

        assert removed == []
        assert link.is_symlink()
        assert (outside / "precious.txt").read_text() == "keep"

    def test_missing_directory_is_a_noop(self, tmp_path):
        assert cleanup_old_uploads(tmp_path / "nope", max_age_days=7) == []

    def test_one_failure_does_not_stop_the_rest(self, tmp_path):
        _make_upload(tmp_path, "a_old", age_days=10)
        _make_upload(tmp_path, "b_old", age_days=10)
        real_rmtree = __import__("shutil").rmtree

        def flaky(path, *args, **kwargs):
            if Path(path).name == "a_old":
                raise OSError("busy")
            return real_rmtree(path, *args, **kwargs)

        with patch("core.uploads.shutil.rmtree", side_effect=flaky):
            removed = cleanup_old_uploads(tmp_path, max_age_days=7)

        assert removed == ["b_old"]
        assert (tmp_path / "a_old").exists() and not (tmp_path / "b_old").exists()

    @pytest.mark.parametrize("bad", [0, -1, 0.5])
    def test_refuses_a_retention_that_could_delete_in_use_files(self, tmp_path, bad):
        _make_upload(tmp_path, "x", age_days=100)

        with pytest.raises(ValueError):
            cleanup_old_uploads(tmp_path, max_age_days=bad)
        assert (tmp_path / "x").exists()


class TestWebuiSweep:
    """webui._sweep_old_uploads: 処理待ち・処理中のアップロードは古くても消さない。"""

    def _setup(self, tmp_path, monkeypatch):
        import webui

        monkeypatch.chdir(tmp_path)
        area = tmp_path / "output" / "uploads"
        monkeypatch.setattr(webui, "UPLOAD_DIR", Path("output/uploads"))
        return webui, area

    def test_keeps_files_of_queued_and_processing_jobs_and_removes_other_old_ones(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from core.webui_workflow import QueueItemState

        webui, area = self._setup(tmp_path, monkeypatch)
        queued = _make_upload(area, "queued", age_days=30)
        done = _make_upload(area, "done", age_days=30)
        recent = _make_upload(area, "recent", age_days=0)

        def item(state, sub):
            res = SimpleNamespace(source_type="local", local_audio_path=str(area / sub / "a.wav"))
            return SimpleNamespace(state=state, resolution=res)

        queue = SimpleNamespace(
            items=[
                item(QueueItemState.QUEUED, "queued"),
                item(QueueItemState.DONE, "done"),
                SimpleNamespace(state=QueueItemState.RESOLVING, resolution=None),
            ]
        )

        webui._sweep_old_uploads(queue)

        assert queued.exists() and recent.exists()
        assert not done.exists()

    def test_failure_does_not_propagate(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        webui, _ = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(webui, "cleanup_old_uploads", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))

        webui._sweep_old_uploads(SimpleNamespace(items=[]))  # 例外を出さない
