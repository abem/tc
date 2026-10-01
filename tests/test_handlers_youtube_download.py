"""
Tests for YouTubeClient.download_audio.

yt-dlp を呼ぶ subprocess は一切モックしない。代わりに tmp_path に置いた
「偽の yt-dlp 実行ファイル」(shebang + 実行権限付きの小さな Python スクリプト)
を client.yt_dlp_path に設定し、本物のサブプロセスとして起動する。
実ネットワークは使わない。subprocess の呼び出し方 (run / Popen、timeout の
有無) に依存しないので、実装の細部が変わっても公開メソッドの入出力だけで検証できる。
"""

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from handlers.youtube import YouTubeClient

YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
X_URL = "https://x.com/user/status/123/video/1"

DEFAULT_INFO = {
    "id": "abc123XYZ",
    "title": "Sample Video",
    "duration": 42,
    "channel": "Sample Channel",
    "upload_date": "20260101",
    "description": "sample description",
}

FAKE_SCRIPT = textwrap.dedent(
    """\
    #!{python}
    import json
    import sys

    CONFIG = json.loads({config!r})
    args = sys.argv[1:]

    with open(CONFIG["call_log"], "a", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\\n")

    if "--dump-json" in args:
        if CONFIG["info_exit"] != 0:
            sys.stderr.write("ERROR: fake info failure\\n")
            sys.exit(CONFIG["info_exit"])
        sys.stdout.write(CONFIG["info_stdout"])
        sys.exit(0)

    out_path = args[args.index("-o") + 1]
    if CONFIG["download_exit"] != 0:
        sys.stderr.write("ERROR: fake download failure\\n")
        sys.exit(CONFIG["download_exit"])

    print("[download]  50.0% of 1.00MiB", flush=True)
    print("[download] 100.0% of 1.00MiB", flush=True)
    if CONFIG["write_suffix"] is not None:
        with open(out_path + CONFIG["write_suffix"], "wb") as f:
            f.write(b"RIFF-fake-wav")
    sys.exit(0)
    """
)


@pytest.fixture
def make_client(tmp_path):
    """偽の yt-dlp を持つ YouTubeClient を作るファクトリ。

    write_suffix:
        None   -> ファイルを作らない
        ""     -> 指定された -o のパスそのものに書く
        ".wav" -> 指定パスに ".wav" を足したパスに書く
    """

    def factory(
        info=DEFAULT_INFO,
        info_stdout=None,
        info_exit=0,
        download_exit=0,
        write_suffix="",
    ):
        out_dir = tmp_path / "out"
        out_dir.mkdir(exist_ok=True)
        call_log = tmp_path / "calls.jsonl"
        config = {
            "call_log": str(call_log),
            "info_exit": info_exit,
            "info_stdout": json.dumps(info) if info_stdout is None else info_stdout,
            "download_exit": download_exit,
            "write_suffix": write_suffix,
        }
        script = tmp_path / "fake-yt-dlp"
        script.write_text(
            FAKE_SCRIPT.format(python=sys.executable, config=json.dumps(config)),
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        client = YouTubeClient(output_dir=str(out_dir))
        client.yt_dlp_path = str(script)
        return client

    return factory


def read_calls(tmp_path: Path):
    log = tmp_path / "calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


class TestDownloadAudioSuccess:
    def test_returns_path_and_metadata(self, make_client, tmp_path):
        """正常系: 出力ファイルが存在し、metadata が偽 yt-dlp の JSON と一致する。"""
        client = make_client()
        explicit = str(tmp_path / "out" / "explicit.wav")

        path, metadata = client.download_audio(YOUTUBE_URL, output_path=explicit)

        assert path == explicit
        assert os.path.exists(path)
        assert metadata["title"] == DEFAULT_INFO["title"]
        assert metadata["video_id"] == DEFAULT_INFO["id"]
        assert metadata["duration"] == DEFAULT_INFO["duration"]
        assert metadata["url"] == YOUTUBE_URL
        assert metadata["channel"] == DEFAULT_INFO["channel"]
        assert metadata["upload_date"] == DEFAULT_INFO["upload_date"]
        assert metadata["description"] == DEFAULT_INFO["description"]

    def test_passes_url_and_output_path_to_yt_dlp(self, make_client, tmp_path):
        """ダウンロード呼び出しに URL と -o の出力パスが渡される。"""
        client = make_client()
        explicit = str(tmp_path / "out" / "explicit.wav")

        client.download_audio(YOUTUBE_URL, output_path=explicit)

        calls = read_calls(tmp_path)
        download_calls = [c for c in calls if "--dump-json" not in c]
        assert len(download_calls) == 1
        args = download_calls[0]
        assert args[-1] == YOUTUBE_URL
        assert args[args.index("-o") + 1] == explicit
        assert args[args.index("--audio-format") + 1] == "wav"

    def test_default_output_path_uses_safe_title_and_video_id(
        self, make_client, tmp_path
    ):
        """output_path 省略時: <output_dir>/<安全化タイトル>_<video_id>.wav になる。"""
        info = dict(DEFAULT_INFO, title="My Video: Test/Clip!  v2", id="vid_001")
        client = make_client(info=info)

        path, _ = client.download_audio(YOUTUBE_URL)

        # 記号は除去され、空白と連続ハイフンは 1 個の "-" にまとまる
        assert path == str(tmp_path / "out" / "My-Video-TestClip-v2_vid_001.wav")
        assert os.path.exists(path)

    def test_default_output_path_truncates_long_title_to_50_chars(
        self, make_client, tmp_path
    ):
        """タイトルは 50 文字に切り詰められ、video_id は切り詰めの後ろに付く。"""
        info = dict(DEFAULT_INFO, title="a" * 80, id="vid_long")
        client = make_client(info=info)

        path, _ = client.download_audio(YOUTUBE_URL)

        assert os.path.basename(path) == "a" * 50 + "_vid_long.wav"

    def test_long_description_is_truncated_to_500_chars(self, make_client):
        """metadata の description は 500 文字までに切り詰められる。"""
        info = dict(DEFAULT_INFO, description="d" * 800)
        client = make_client(info=info)

        _, metadata = client.download_audio(YOUTUBE_URL)

        assert metadata["description"] == "d" * 500

    def test_missing_info_fields_fall_back_to_defaults(self, make_client, tmp_path):
        """title/id 以外が欠けている JSON でも既定値で metadata を返す。"""
        client = make_client(info={"id": "only_id"})

        path, metadata = client.download_audio(YOUTUBE_URL)

        assert os.path.basename(path) == "unknown_only_id.wav"
        assert metadata["title"] == "unknown"
        assert metadata["video_id"] == "only_id"
        assert metadata["duration"] == 0
        assert metadata["channel"] == "unknown"
        assert metadata["upload_date"] == "unknown"
        assert metadata["description"] == ""

    @pytest.mark.parametrize("url", [YOUTUBE_URL, X_URL])
    def test_accepts_youtube_and_x_urls(self, make_client, tmp_path, url):
        """YouTube と X(Twitter) の両方の URL を受け付け、その URL を yt-dlp に渡す。"""
        client = make_client()

        path, metadata = client.download_audio(url)

        assert os.path.exists(path)
        assert metadata["url"] == url
        assert all(c[-1] == url for c in read_calls(tmp_path))


class TestDownloadAudioFailures:
    def test_nonzero_exit_raises_runtime_error(self, make_client, tmp_path):
        """yt-dlp が非 0 で終了したら RuntimeError。stderr の内容がメッセージに入る。"""
        client = make_client(download_exit=1)
        target = tmp_path / "out" / "fail.wav"

        with pytest.raises(RuntimeError, match="Audio extraction failed") as excinfo:
            client.download_audio(YOUTUBE_URL, output_path=str(target))

        assert "fake download failure" in str(excinfo.value)
        assert not target.exists()

    def test_unsupported_url_raises_value_error_without_running_yt_dlp(
        self, make_client, tmp_path
    ):
        """対応外 URL は ValueError。yt-dlp は一度も起動されない。"""
        client = make_client()

        with pytest.raises(ValueError, match="Unsupported URL"):
            client.download_audio("https://example.com/video")

        assert read_calls(tmp_path) == []

    def test_info_command_failure_raises_runtime_error(self, make_client, tmp_path):
        """メタデータ取得が失敗したら RuntimeError。ダウンロードは行われない。"""
        client = make_client(info_exit=1)

        with pytest.raises(RuntimeError, match="Failed to get video info"):
            client.download_audio(YOUTUBE_URL)

        assert all("--dump-json" in c for c in read_calls(tmp_path))

    @pytest.mark.parametrize("stdout", ["this is not json", "{}"])
    def test_unusable_info_output_raises_runtime_error(self, make_client, stdout):
        """メタデータが JSON でない / 空 dict のときも RuntimeError。"""
        client = make_client(info_stdout=stdout)

        with pytest.raises(RuntimeError, match="Failed to get video info"):
            client.download_audio(YOUTUBE_URL)


class TestDownloadAudioOutputFilename:
    def test_falls_back_to_path_with_wav_appended(self, make_client, tmp_path):
        """yt-dlp が <指定パス>.wav に書いた場合は、そのパスが返る。"""
        client = make_client(write_suffix=".wav")
        requested = tmp_path / "out" / "audio.wav"

        path, _ = client.download_audio(YOUTUBE_URL, output_path=str(requested))

        assert path == str(requested) + ".wav"
        assert os.path.exists(path)
        assert not requested.exists()

    def test_falls_back_when_requested_path_has_no_extension(
        self, make_client, tmp_path
    ):
        """拡張子なしの指定でも <指定パス>.wav に書かれていれば、そのパスが返る。"""
        client = make_client(write_suffix=".wav")
        requested = tmp_path / "out" / "audio"

        path, _ = client.download_audio(YOUTUBE_URL, output_path=str(requested))

        assert path == str(requested) + ".wav"
        assert os.path.exists(path)

    def test_missing_output_file_raises_file_not_found(self, make_client, tmp_path):
        """どの候補パスにも出力が無ければ FileNotFoundError。"""
        client = make_client(write_suffix=None)
        requested = tmp_path / "out" / "nothing.wav"

        with pytest.raises(FileNotFoundError, match="Output file not found"):
            client.download_audio(YOUTUBE_URL, output_path=str(requested))
