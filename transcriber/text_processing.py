"""
Text processing functionality extracted from WhisperTranscriber.
Handles text formatting, segmentation, and linguistic processing.
"""

import re
from typing import List, Dict, Any, Optional

try:
    from spacy.tokens import Span
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    Span = None


class TextProcessor:
    """Handles text processing and formatting for transcription results."""
    
    # 言語学的フォーマット用定数
    STRICT_PUNCTUATIONS = ["。", "！", "？", "…"]
    STRONG_SENTENCE_ENDINGS_WITHOUT_PUNCT = [
        "です", "ます", "でした", "ました", "である", "だ", "である", "です", "ます"
    ]
    DEFAULT_MAX_LINE_LENGTH = 80
    
    def __init__(self, max_line_length: int = 80):
        self.max_line_length = max_line_length
    
    def format_text_linguistically(self, text: str, max_line_length: Optional[int] = None) -> str:
        """言語学的に自然な改行を入れたテキスト整形"""
        if max_line_length is None:
            max_line_length = self.max_line_length
        
        if not text or not text.strip():
            return ""
        
        # 基本的な正規化
        text = self._normalize_text(text)
        
        # 文区切りで分割
        sentences = self._split_into_sentences(text)
        
        # 行長制限を適用
        formatted_lines = []
        for sentence in sentences:
            if len(sentence) <= max_line_length:
                formatted_lines.append(sentence)
            else:
                # 長い文は適切に分割
                sub_lines = self._split_long_sentence(sentence, max_line_length)
                formatted_lines.extend(sub_lines)
        
        return "\n".join(formatted_lines)
    
    def _normalize_text(self, text: str) -> str:
        """テキストの基本正規化"""
        # 連続する空白を単一スペースに
        text = re.sub(r'\s+', ' ', text)
        
        # 前後の空白を削除
        text = text.strip()
        
        return text
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """文単位での分割"""
        sentences = []
        current_sentence = ""
        
        words = text.split()
        
        for word in words:
            current_sentence += word + " "
            
            # 文終了の判定
            if self._is_sentence_end(word):
                sentences.append(current_sentence.strip())
                current_sentence = ""
        
        # 残りがあれば追加
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        return sentences
    
    def _is_sentence_end(self, word: str) -> bool:
        """文終了の判定"""
        # 明確な句読点がある場合
        for punct in self.STRICT_PUNCTUATIONS:
            if word.endswith(punct):
                return True
        
        # 強い文終了表現
        for ending in self.STRONG_SENTENCE_ENDINGS_WITHOUT_PUNCT:
            if word.endswith(ending):
                return True
        
        return False
    
    def _split_long_sentence(self, sentence: str, max_length: int) -> List[str]:
        """長い文の適切な分割"""
        if len(sentence) <= max_length:
            return [sentence]
        
        words = sentence.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            
            if len(test_line) <= max_length:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def create_segments_with_timestamps(self, 
                                      text: str, 
                                      segments: List[Dict[str, Any]],
                                      timestamp_format: str = "elapsed") -> str:
        """タイムスタンプ付きセグメント作成"""
        if not segments:
            return text
        
        formatted_segments = []
        
        for segment in segments:
            timestamp = self._format_timestamp(
                segment.get('start', 0), 
                timestamp_format
            )
            
            segment_text = segment.get('text', '').strip()
            if segment_text:
                formatted_segments.append(f"[{timestamp}] {segment_text}")
        
        return "\n".join(formatted_segments)
    
    def _format_timestamp(self, seconds: float, format_type: str = "elapsed") -> str:
        """タイムスタンプのフォーマット"""
        if format_type == "elapsed":
            minutes = int(seconds // 60)
            seconds = int(seconds % 60)
            return f"{minutes:02d}:{seconds:02d}"
        elif format_type == "absolute":
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            seconds = int(seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{seconds:.1f}s"
    
    def extract_key_phrases(self, text: str, max_phrases: int = 10) -> List[str]:
        """キーフレーズの抽出（簡易版）"""
        if not text:
            return []
        
        # 基本的な名詞句抽出（日本語対応）
        words = text.split()
        phrases = []
        
        # 長めの単語をキーフレーズとして抽出
        for word in words:
            if len(word) >= 3 and word not in phrases:
                phrases.append(word)
        
        return phrases[:max_phrases]
    
    def calculate_text_metrics(self, text: str) -> Dict[str, Any]:
        """テキストメトリクスの計算"""
        if not text:
            return {
                'character_count': 0,
                'word_count': 0,
                'line_count': 0,
                'sentence_count': 0
            }
        
        lines = text.split('\n')
        words = text.split()
        sentences = self._split_into_sentences(text)
        
        return {
            'character_count': len(text),
            'word_count': len(words),
            'line_count': len(lines),
            'sentence_count': len(sentences),
            'avg_line_length': sum(len(line) for line in lines) / len(lines) if lines else 0,
            'avg_sentence_length': len(text) / len(sentences) if sentences else 0
        }