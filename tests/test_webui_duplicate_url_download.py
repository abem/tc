"""
Tests for the tc-ops #440是正・不具合2 (同一URL重複投入時のダウンロード出力パス衝突)。

`handlers.youtube.YouTubeClient.download_audio()`(`output_path`未指定時に`{safe_title}_{video_id}.wav`
という完全に決定的なパスを`self.output_dir`配下に生成する、L111-115)をモックし、
`core.cli_workflow.resolve_input_audio()`(無変更の既存関数)へ渡す`output_dir`が異なれば
同一URL(同一動画情報)でも衝突しないこと、同一`output_dir`のままなら衝突すること(是正前の
webui.pyの挙動を再現する対照ケース)の両方を検証する。

`webui.py`自体はStreamlit依存のため直接ユニットテスト対象に含めない(tc-ops #440時点と同じ
テスト境界を踏襲、予備調査完了報告2-3節)。
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.cli_workflow import resolve_input_audio

SAME_URL = "https://www.youtube.com/watch?v=abc123"


def _make_fake_download_audio(deterministic_filename: str):
    """`handlers/youtube.py` L111-115 の決定論理(output_path未指定時の挙動)を模したフェイク。"""

    def _fake_download_audio(self, url, output_path=None):
        if output_path is None:
            output_path = os.path.join(self.output_dir, deterministic_filename)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).touch()
        return output_path, {"title": "Same Video", "video_id": "abc123", "duration": 10, "url": url}

    return _fake_download_audio


class TestDuplicateUrlDownloadPathCollision:
    def test_duplicate_url_with_same_download_dir_collides_illustrating_the_bug(self, tmp_path):
        """是正前のwebui.py(常に同一output_dirを渡す)を再現する対照ケース: 2回目が1回目の
        ファイルを上書きし、1回目のパス参照が壊れる(is-broken-without-fixのレグレッション網)。"""
        shared_dir = tmp_path / "shared"
        fake = _make_fake_download_audio("Same-Video_abc123.wav")
        with patch("handlers.youtube.YouTubeClient.download_audio", fake):
            res1 = resolve_input_audio(SAME_URL, shared_dir, ensure_yt_dlp=False)
            path1_before_second_call = res1.local_audio_path
            res2 = resolve_input_audio(SAME_URL, shared_dir, ensure_yt_dlp=False)

        assert res1.local_audio_path == res2.local_audio_path == path1_before_second_call
        # 1件目完了時のcleanupが2件目のファイルも道連れに削除する(tc-ops #440是正の背景そのもの)
        os.remove(res1.local_audio_path)
        assert not Path(res2.local_audio_path).exists()

    def test_duplicate_url_with_distinct_download_dirs_does_not_collide(self, tmp_path):
        """是正後のwebui.py(投入ごとに一意なdownload_dirを発行)を模す: 同一URL・同一動画情報でも
        2件のQueueItemが異なるファイルを持ち、片方のcleanupがもう片方に波及しない。"""
        dir1 = tmp_path / "queue_downloads" / "aaaaaaaa"
        dir2 = tmp_path / "queue_downloads" / "bbbbbbbb"
        fake = _make_fake_download_audio("Same-Video_abc123.wav")
        with patch("handlers.youtube.YouTubeClient.download_audio", fake):
            res1 = resolve_input_audio(SAME_URL, dir1, ensure_yt_dlp=False)
            res2 = resolve_input_audio(SAME_URL, dir2, ensure_yt_dlp=False)

        assert res1.local_audio_path != res2.local_audio_path
        assert Path(res1.local_audio_path).exists()
        assert Path(res2.local_audio_path).exists()

        os.remove(res1.local_audio_path)
        assert not Path(res1.local_audio_path).exists()
        assert Path(res2.local_audio_path).exists()  # 1件目のcleanupが2件目へ波及しない
