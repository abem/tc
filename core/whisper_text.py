"""
Whisper エンジンのテキスト整形(純粋関数)。

[MM:SS] 形式のタイムスタンプ付きテキストの解析・付与・行頭正規化と、
音声配列のチャンク分割。WhisperTranscriptionEngine のメソッドから委譲される。
"""

import re
from typing import List, Optional

from core.transcription_types import TranscriptionSegment

__all__ = [
    "parse_timestamped_text",
    "add_timestamps_to_text",
    "ensure_timestamps_at_line_start",
    "create_chunks",
]

_TIMESTAMP_SEGMENT_PATTERN = r'\[(\d{2}):(\d{2})\]\s*(.+?)(?=\[|\Z)'


def parse_timestamped_text(
    text: str, language: Optional[str], fallback_duration: float
) -> List[TranscriptionSegment]:
    """Parse timestamped text into segments.

    タイムスタンプが無い場合は、全体を 1 セグメント(長さ fallback_duration)にする。
    """
    segments = []

    # Pattern to match [MM:SS] timestamp format
    matches = re.findall(_TIMESTAMP_SEGMENT_PATTERN, text, re.DOTALL)

    for minutes, seconds, segment_text in matches:
        start_time = int(minutes) * 60 + int(seconds)

        segment = TranscriptionSegment(
            start=start_time,
            end=start_time + 30,  # Default 30-second segments
            text=segment_text.strip(),
            language=language
        )
        segments.append(segment)

    # If no timestamps found, create single segment
    if not segments and text.strip():
        segments = [TranscriptionSegment(
            start=0.0,
            end=fallback_duration,
            text=text.strip(),
            language=language
        )]

    return segments


def add_timestamps_to_text(text: str, start_seconds: int) -> str:
    """Add timestamps to text segments."""
    if not text.strip():
        return ""

    # Format timestamp as [MM:SS]
    minutes = start_seconds // 60
    seconds = start_seconds % 60
    timestamp = f"[{minutes:02d}:{seconds:02d}]"

    # Clean and format text
    text = text.strip()
    return f"{timestamp} {text}"


def ensure_timestamps_at_line_start(text: str) -> str:
    """Ensure timestamps are at the beginning of lines."""
    # Split into lines and process each
    lines = text.split('\n')
    processed_lines = []

    for line in lines:
        line = line.strip()
        if line:
            # Ensure timestamp is at the start
            if not line.startswith('['):
                # Look for timestamp pattern in the line
                timestamp_match = re.search(r'\[(\d{2}):(\d{2})\]', line)
                if timestamp_match:
                    timestamp = timestamp_match.group(0)
                    text_part = line.replace(timestamp, '').strip()
                    line = f"{timestamp} {text_part}"
            processed_lines.append(line)

    return '\n'.join(processed_lines)


def create_chunks(audio, chunk_size):
    """Create audio chunks for processing."""
    chunks = []
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i:i + chunk_size]
        if len(chunk) > 0:
            chunks.append(chunk)
    return chunks
