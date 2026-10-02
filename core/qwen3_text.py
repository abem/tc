"""
Qwen3-ASR エンジンのテキスト整形・解析(純粋関数)。

反復ループ検出、文節改行、ForcedAligner 出力との対応付け、言語名変換。
Qwen3ASREngine の静的メソッドから委譲される(検出ロジック・閾値は不変)。
"""

import re
import unicodedata
from typing import Optional, Tuple

__all__ = [
    "core_char_count",
    "match_fragments_to_alignment",
    "detect_repetition",
    "format_text_with_breaks",
    "language_name_to_code",
]


def core_char_count(text: str) -> int:
    """句読点等を除いた実質文字数。ForcedAlignerは句読点を除去した実質
    文字/単語単位でトークン化するため、フラグメントとアライナー出力の
    対応付け(_match_fragments_to_alignment)の消費量算出に使う。
    """

    count = 0
    for ch in text:
        if ch == "'":
            count += 1
            continue
        category = unicodedata.category(ch)
        if category.startswith("L") or category.startswith("N"):
            count += 1
    return count


def match_fragments_to_alignment(fragments, align_items):
    """文節フラグメント列(_format_text_with_breaksと同じ区切り)を
    ForcedAlignerの出力アイテム列に近似的に対応付け、各フラグメントの
    (start_time, end_time)のリストを返す。

    ForcedAlignerは句読点を除いた実質文字/単語単位でトークン化するため、
    各フラグメントの実質文字数ぶんアイテムを順に消費し、先頭アイテムの
    start_timeと消費末尾アイテムのend_timeを区間として採用する。厳密な
    1対1対応の保証はない近似処理(音声位置の目安として十分な精度)。
    """
    results = []
    idx = 0
    n = len(align_items)
    for frag in fragments:
        target = core_char_count(frag)
        if target == 0 or idx >= n:
            prev_end = results[-1][1] if results else 0.0
            results.append((prev_end, prev_end))
            continue
        start_idx = idx
        consumed = 0
        while idx < n and consumed < target:
            consumed += len(align_items[idx].text)
            idx += 1
        end_idx = max(idx - 1, start_idx)
        results.append((align_items[start_idx].start_time, align_items[end_idx].end_time))
    return results


def detect_repetition(text: str, max_cycle: int = 40, min_repeats: int = 3) -> Tuple[bool, Optional[int]]:
    """句読点区切りの文節列に、同一の文節シーケンス(長さ1〜max_cycle)が
    min_repeats回以上連続して繰り返される箇所がないかを検出する。

    ASRの反復ループ(実障害: 「アジェンツは、ツールコールの高品質と正確さを
    必要とするため...」という1文が単語単位の改行を伴い70回以上連続反復)を
    検知するための軽量ヒューリスティック。正規表現の後方参照
    (`(.+)\\1{2,}`)はバックトラック爆発のリスクがあるため使わず、
    文節リストに対する固定長スライド窓比較で実装する。

    戻り値: (反復を検出したか, 反復が開始する文字インデックス[検出時のみ、
    テキスト先頭からの文字オフセット。未検出時はNone])。反復開始位置は
    tc-ops #547是正(2026-09-27、(c)反復部分のみ除去)で追加した。呼び出し元は
    `text[:pos]`で反復開始前の正常テキストのみを残せる。
    """

    fragments = [s for s in re.split(r'(?<=[。、！？!?])', text) if s.strip()]
    n = len(fragments)
    if n < min_repeats:
        return False, None

    for cycle in range(1, max_cycle + 1):
        window_span = cycle * min_repeats
        if n < window_span:
            break
        for i in range(0, n - window_span + 1):
            unit = fragments[i:i + cycle]
            if all(
                fragments[i + k * cycle:i + (k + 1) * cycle] == unit
                for k in range(1, min_repeats)
            ):
                position = sum(len(f) for f in fragments[:i])
                return True, position
    return False, None


def format_text_with_breaks(text: str) -> str:
    """テキストを文節区切りで改行する。

    句点(。)・読点(、)・感嘆符(！/!)・疑問符(？/?) の後に改行を入れる。
    タイムスタンプは付与しない(実時間の精度に確証がないため誤解を避ける)。
    """

    # 文節区切り文字で分割(区切り文字も保持)
    sentences = re.split(r'(?<=[。、！？!?])', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return text.strip()

    return "\n".join(sentences)


def language_name_to_code(name: Optional[str]) -> str:
    """'Japanese' -> 'ja' のように言語名をコードに変換。"""
    mapping = {"japanese": "ja", "english": "en"}
    return mapping.get((name or "").lower(), name or "ja")
