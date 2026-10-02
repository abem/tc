#!/usr/bin/env python3
"""
YouTube audio extraction client.
"""

import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from core.logging import get_logger
from core.progress import emit_progress, parse_ytdlp_progress
from core.utils import is_youtube_url as check_is_youtube_url
from core.utils import is_twitter_url as check_is_twitter_url

logger = get_logger(__name__)

# tc-ops #550是正: yt-dlp呼び出しはtimeout未設定だとフラグメント取得等の単発通信が停止した際に
# 無期限に待機してしまう(WebUI「解決中」ハングの原因候補)。
SOCKET_TIMEOUT_SECONDS = 30  # yt-dlp --socket-timeout。単発通信の無応答をyt-dlp自身に検知させる。
INFO_TIMEOUT_SECONDS = 60  # extract_video_info()のsubprocess.run全体タイムアウト。メタデータ取得は実測0.9秒程度のため十分な余裕を持たせた値。
DOWNLOAD_STALL_TIMEOUT_SECONDS = 300  # download_audio()の出力停止監視。--socket-timeoutでは捕捉できない非ネットワーク要因(後段処理のハング等)への保険。


class YouTubeClient:
    """YouTube audio extraction client."""

    def __init__(self, output_dir: Optional[str] = None):
        """
        Args:
            output_dir: Output directory for temporary files
        """
        self.output_dir = output_dir or tempfile.gettempdir()
        self.yt_dlp_path = self._find_yt_dlp()

    def _find_yt_dlp(self) -> str:
        """Find yt-dlp executable path (見つからなければコマンド名のまま返す)。"""
        return find_yt_dlp() or "yt-dlp"

    def is_youtube_url(self, url: str) -> bool:
        """Check if URL is a YouTube URL."""
        return check_is_youtube_url(url)

    def is_supported_url(self, url: str) -> bool:
        """Check if URL is a yt-dlp-backed URL supported by this client(YouTube/X)."""
        return check_is_youtube_url(url) or check_is_twitter_url(url)

    def extract_video_info(self, url: str) -> Dict:
        """Get video information."""
        try:
            cmd = [
                self.yt_dlp_path,
                "--dump-json",
                "--no-playlist",
                "--socket-timeout", str(SOCKET_TIMEOUT_SECONDS),
                url
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=INFO_TIMEOUT_SECONDS
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                logger.error(f"Failed to get video info: {result.stderr}")
                return {}

        except subprocess.TimeoutExpired:
            logger.error(f"Timed out getting video info ({INFO_TIMEOUT_SECONDS}s): {url}")
            return {}
        except Exception as e:
            logger.error(f"Error extracting video info: {e}")
            return {}

    def download_audio(
        self,
        url: str,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[str, Dict]:
        """
        Download and extract audio from a YouTube or X(Twitter) video.

        Args:
            url: YouTube or X(Twitter) video URL
            output_path: Output file path (auto-generated if None)

        Returns:
            Tuple of (audio_file_path, metadata)
        """
        if not self.is_supported_url(url):
            raise ValueError(f"Unsupported URL (YouTube/X only): {url}")

        video_info = self.extract_video_info(url)
        if not video_info:
            raise RuntimeError("Failed to get video info")

        video_title = video_info.get('title', 'unknown')
        video_id = video_info.get('id', 'unknown')
        duration = video_info.get('duration', 0)

        logger.info(f"Video title: {video_title}")
        logger.info(f"Video duration: {duration}s")

        if output_path is None:
            safe_title = re.sub(r'[^\w\s-]', '', video_title)
            safe_title = re.sub(r'[-\s]+', '-', safe_title)[:50]
            output_filename = f"{safe_title}_{video_id}.wav"
            output_path = os.path.join(self.output_dir, output_filename)

        cmd = [
            self.yt_dlp_path,
            "-x",
            "--audio-format", "wav",
            "--audio-quality", "0",
            "--no-playlist",
            "--socket-timeout", str(SOCKET_TIMEOUT_SECONDS),
            "-o", output_path,
            "--quiet",
            "--no-warnings",
            "--progress",
            "--newline",
            url
        ]

        try:
            logger.info(f"Starting audio extraction: {url}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            last_percent = -1
            notified_converting = False
            sel = selectors.DefaultSelector()
            sel.register(process.stdout, selectors.EVENT_READ)

            while True:
                events = sel.select(timeout=DOWNLOAD_STALL_TIMEOUT_SECONDS)
                if not events:
                    process.kill()
                    process.wait()
                    raise TimeoutError(
                        f"yt-dlp出力が{DOWNLOAD_STALL_TIMEOUT_SECONDS}秒間停止したため中断: {url}"
                    )
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    if "[download]" in output and "%" in output:
                        print(f"\r{output.strip()}", end='', flush=True)
                    parsed = parse_ytdlp_progress(output)
                    if parsed is not None:
                        fraction, eta = parsed
                        percent = int(fraction * 100)
                        if percent != last_percent:
                            last_percent = percent
                            suffix = f"(残り {eta})" if eta else ""
                            emit_progress(progress_callback, f"ダウンロード中 {percent}%{suffix}", fraction)
                        if fraction >= 1.0 and not notified_converting:
                            notified_converting = True
                            emit_progress(progress_callback, "音声をwavに変換中(長い動画は数分かかります)")

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"Audio extraction failed: {stderr}")

            if not os.path.exists(output_path):
                possible_paths = [
                    output_path,
                    output_path + ".wav",
                    output_path.replace(".wav", ".wav.wav")
                ]

                for path in possible_paths:
                    if os.path.exists(path):
                        output_path = path
                        break
                else:
                    raise FileNotFoundError(f"Output file not found: {output_path}")

            logger.info(f"Audio extraction complete: {output_path}")

            metadata = {
                'title': video_title,
                'video_id': video_id,
                'duration': duration,
                'url': url,
                'channel': video_info.get('channel', 'unknown'),
                'upload_date': video_info.get('upload_date', 'unknown'),
                'description': video_info.get('description', '')[:500]
            }

            return output_path, metadata

        except subprocess.CalledProcessError as e:
            logger.error(f"yt-dlp command failed: {e}")
            raise RuntimeError(f"Audio extraction failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

    def cleanup_temp_file(self, file_path: str):
        """Remove temporary file."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Temporary file removed: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to remove temporary file: {e}")


class YtDlpNotFoundError(ValueError):
    """yt-dlp が見つからない。自動インストールはせず、対処(uv sync)を案内して止める(D6)。

    tc は ValueError を「入力を解決できない」として exit 1 で処理するため ValueError を継承する。
    """


def find_yt_dlp() -> Optional[str]:
    """yt-dlp 実行ファイルの検出(唯一の方法)。見つからなければ None。

    優先順: PATH(`shutil.which`)→ 現在の Python と同じ `bin/`(uv の `.venv` を
    `uv run` を介さず直接呼んだ場合)→ カレントの `.venv/bin/yt-dlp`。
    `YouTubeClient.yt_dlp_path` と `check_yt_dlp_installed()` はどちらもこれを使う。
    """
    found = shutil.which("yt-dlp")
    if found:
        return found

    candidates = [
        Path(sys.executable).parent / "yt-dlp",
        Path(".venv/bin/yt-dlp"),
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def check_yt_dlp_installed() -> bool:
    """Check if yt-dlp is installed (`find_yt_dlp` と同じ検出)。"""
    return find_yt_dlp() is not None
