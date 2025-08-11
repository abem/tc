from typing import List, Dict
import re
import sys
try:
    import spacy
    nlp = spacy.load('ja_ginza')
except Exception as e:
    print(f"[FATAL] GiNZAロード失敗: {e}", file=sys.stderr)
    raise

print('RELOADED', flush=True)

MAX_LINE_LENGTH = 10000  # 実質無効化

def debug_log(msg):
    with open('debug_text_formatter_output.txt', 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def fallback_sentence_split(text):
    # 句点・改行・読点で強制分割
    sents = re.split(r'[。\n、,]', text)
    sents = [s.strip() for s in sents if s.strip()]
    result = []
    for s in sents:
        if len(s) > MAX_LINE_LENGTH:
            print(f"[DEBUG] fallback: 長文を20文字ごとに強制分割: {s}")
            for i in range(0, len(s), 20):
                result.append(s[i:i+20])
        else:
            result.append(s)
    print(f"[DEBUG] fallback_sentence_split最終結果: {result}")
    return result

def ginza_bunsetu_split(text):
    # GiNZAで形態素解析し、助詞・助動詞・接続詞・読点で分節的にsplit
    if nlp is None:
        return [text]
    doc = nlp(text)
    bunsetsu = []
    buf = ''
    for token in doc:
        buf += token.text
        if token.pos_ in ['ADP', 'AUX', 'CCONJ', 'SCONJ', 'PUNCT']:
            bunsetsu.append(buf)
            buf = ''
    if buf:
        bunsetsu.append(buf)
    return [b.strip() for b in bunsetsu if b.strip()]

def ginza_desumasu_split(text):
    if nlp is None:
        return [text]
    doc = nlp(text)
    result = []
    buf = ''
    desumasu_words = {'です', 'ます', 'でした', 'ました', 'でしょう', 'だろう', 'である', 'だ', 'だった'}
    for token in doc:
        buf += token.text
        if token.text in desumasu_words:
            result.append(buf)
            buf = ''
    if buf:
        result.append(buf)
    return [b.strip() for b in result if b.strip()]

def ginza_mecab_style_split(text):
    if nlp is None:
        return [text]
    doc = nlp(text)
    result = []
    buf = ''
    split_pos = {'AUX', 'ADP', 'PUNCT'}  # 助動詞・助詞・句読点
    desumasu_words = {'です', 'ます', 'でした', 'ました', 'でしょう', 'だろう', 'である', 'だ', 'だった'}
    for token in doc:
        buf += token.text
        # 品詞または語でsplit
        if token.pos_ in split_pos or token.text in desumasu_words:
            result.append(buf)
            buf = ''
    if buf:
        result.append(buf)
    return [b.strip() for b in result if b.strip()]

def is_linguistic_break_trigger(token, tokens, token_idx, current_line_buffer, max_line_length):
    next_token = tokens[token_idx + 1] if token_idx + 1 < len(tokens) else None
    # 強い句読点
    if token.text in ['。', '！', '？', '!', '?']:
        return True
    if token.tag_ in ['記号-句点', '補助記号-句点']:
        return True
    # 助詞・助動詞・接続詞・読点直後は絶対に改行しない
    if token.pos_ in ['ADP', 'AUX', 'CCONJ', 'SCONJ', 'PUNCT']:
        return False
    # 文節末かつ係り受けが切れる場合のみ改行
    is_bunsetu_end = hasattr(token, 'bunsetu_position_type_') and token.bunsetu_position_type_ in ["文節末", "末"]
    is_dep_break = False
    if next_token:
        if getattr(token, 'dep_', '') in ['ROOT', 'punct']:
            is_dep_break = True
        elif getattr(token, 'head', None) and token.head != next_token.head:
            is_dep_break = True
    else:
        is_dep_break = True  # 文末
    if is_bunsetu_end and is_dep_break:
        return True
    # MAX_LINE_LENGTH超過時も文節末以外では改行しない
    # 文末
    if token_idx == len(tokens) - 1:
        return True
    return False

def _append_line_with_force_split(lines, line, start, end, force_split_reason=None):
    text_only = line
    if line.startswith('['):
        try:
            text_only = line.split(']', 1)[1].strip()
        except Exception:
            text_only = line
    h1, m1, s1 = int(start // 3600), int((start % 3600) // 60), int(start % 60)
    h2, m2, s2 = int(end // 3600), int((end % 3600) // 60), int(end % 60)
    debug_log(f"[DEBUG] TS: start={start}, end={end}, h1={h1}, m1={m1}, s1={s1}, h2={h2}, m2={m2}, s2={s2}")
    ts1 = f"{h1:02}:{m1:02}:{s1:02}"
    ts2 = f"{h2:02}:{m2:02}:{s2:02}"
    out_line = f"[{ts1} -> {ts2}] {text_only}"
    debug_log(f"[DEBUG] append: {out_line} (len={len(text_only)})")
    lines.append(out_line)

class TextFormatter:
    def __init__(self):
        pass

    def format(self, segments: List[Dict], output_format: str = 'txt') -> str:
        """
        セグメントリストを指定フォーマット（txt, srt, vtt, json等）に整形して返す
        タイムスタンプ付きテキストを保持したまま出力
        """
        if output_format == 'txt':
            lines = []
            for seg in segments:
                text = seg.get('text', '').strip()
                text = re.sub(r'<\|[0-9.]+\|>', '', text)
                
                # タイムスタンプ修正機能を適用
                text = self._ensure_timestamps_at_line_start(text)
                
                # 改行で分割して各行を追加
                for line in text.split('\n'):
                    line = line.strip()
                    if line:
                        lines.append(line)
            
            return '\n'.join(lines)
        raise NotImplementedError(f"TextFormatter.format()未対応: {output_format}")
    
    def _ensure_timestamps_at_line_start(self, text):
        """タイムスタンプが確実に行頭に配置されるようにテキストを整形"""
        if not text:
            return text
        
        # 既存のタイムスタンプパターンを検出
        timestamp_pattern = r'\[\d{2}:\d{2}:\d{2}\]'
        
        # 各行を処理
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # 行内のすべてのタイムスタンプを抽出
            timestamps = re.findall(timestamp_pattern, line)
            if not timestamps:
                # タイムスタンプがない場合はそのまま
                lines.append(line)
                continue
            
            # タイムスタンプ以外のテキストを抽出
            content = re.sub(timestamp_pattern, '', line)
            content = re.sub(r'\s+', ' ', content).strip()  # 複数の空白を単一の空白に
            
            if content:
                # 最初のタイムスタンプを行頭に配置
                lines.append(f"{timestamps[0]} {content}")
            else:
                # 内容がない場合は最初のタイムスタンプのみ
                lines.append(timestamps[0])
        
        return '\n'.join(lines) 