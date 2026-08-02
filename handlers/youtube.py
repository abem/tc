#!/usr/bin/env python3
"""
YouTube audio extraction client.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

from core.logging import get_logger
from core.utils import is_youtube_url as check_is_youtube_url
from core.utils import is_twitter_url as check_is_twitter_url

logger = get_logger(__name__)


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
        """Find yt-dlp executable path."""
        # Check .venv first (uv が管理する仮想環境)
        venv_path = Path(".venv/bin/yt-dlp")
        if venv_path.exists():
            return str(venv_path)

        # Check system
        try:
            result = subprocess.run(
                ["which", "yt-dlp"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return "yt-dlp"

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
                url
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                logger.error(f"Failed to get video info: {result.stderr}")
                return {}

        except Exception as e:
            logger.error(f"Error extracting video info: {e}")
            return {}

    def download_audio(
        self,
        url: str,
        output_path: Optional[str] = None
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
            "-o", output_path,
            "--quiet",
            "--no-warnings",
            "--progress",
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

            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    if "[download]" in output and "%" in output:
                        print(f"\r{output.strip()}", end='', flush=True)

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


def check_yt_dlp_installed() -> bool:
    """Check if yt-dlp is installed."""
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_yt_dlp():
    """Install yt-dlp."""
    try:
        logger.info("Installing yt-dlp...")
        subprocess.run(["pip", "install", "yt-dlp"], check=True)
        logger.info("yt-dlp installed successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"yt-dlp installation failed: {e}")
        raise


# Legacy alias for backward compatibility
YouTubeHandler = YouTubeClient
