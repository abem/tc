"""
モデル名による文字起こしエンジンの選択(判定の単一の置き場)。

判定順は nemotron -> qwen3-asr -> whisper(tc-ops #546 Phase2設計report§2)。
is_nemotron_model / Qwen3ASREngine.is_qwen3_model の判定文字列は互いに排他的なため、
この順序自体は既存モデル名の解決結果に影響しない。
"""

from core.config import TranscriptionConfig
from core.nemotron_engine import NemotronSubprocessEngine, is_nemotron_model
from core.qwen3_engine import Qwen3ASREngine
from core.transcription_types import TranscriptionEngine
from core.whisper_engine import WhisperTranscriptionEngine

__all__ = ["create_engine"]


def create_engine(config: TranscriptionConfig) -> TranscriptionEngine:
    """config.model からエンジンを生成する。"""
    if is_nemotron_model(config.model):
        return NemotronSubprocessEngine(config)
    if Qwen3ASREngine.is_qwen3_model(config.model):
        return Qwen3ASREngine(config)
    return WhisperTranscriptionEngine(config)
