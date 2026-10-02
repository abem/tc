"""進捗通知の共通部品(WebUIの進捗バー用)。

進捗コールバックは従来どおり `Callable[[str], None]`。進捗率を持つ通知は `ProgressMessage`
(`str`のサブクラス)で渡すので、文字列だけを受け取る既存のコールバックや表示にもそのまま使える。
"""

import re
from typing import Any, Callable, Optional

_YTDLP_PERCENT_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_YTDLP_ETA_RE = re.compile(r"ETA\s+(\S+)")


class ProgressMessage(str):
    """進捗率付きの進捗メッセージ。`fraction`は0.0〜1.0、`None`は「率は不明(処理中表示のみ)」。"""

    fraction: Optional[float]

    def __new__(cls, text: str, fraction: Optional[float] = None) -> "ProgressMessage":
        obj = super().__new__(cls, text)
        obj.fraction = None if fraction is None else min(max(float(fraction), 0.0), 1.0)
        return obj


def emit_progress(callback: Optional[Callable[[str], Any]], text: str, fraction: Optional[float] = None) -> None:
    """進捗を通知する。コールバック側の例外で本処理(文字起こし・ダウンロード)を止めない。"""
    if callback is None:
        return
    try:
        callback(ProgressMessage(text, fraction))
    except Exception:
        pass


def parse_ytdlp_progress(line: str) -> Optional[tuple[float, Optional[str]]]:
    """yt-dlpの進捗行(`[download]  12.3% of ... ETA 00:42`)から(進捗率0.0〜1.0, ETA文字列)を取り出す。
    進捗行でなければ`None`。"""
    m = _YTDLP_PERCENT_RE.search(line)
    if not m:
        return None
    eta = _YTDLP_ETA_RE.search(line)
    return min(float(m.group(1)) / 100.0, 1.0), (eta.group(1) if eta else None)


def throttled(printer: Callable[[str], Any], steps: int = 10) -> Callable[[str], Any]:
    """CLI用: 進捗率つきメッセージは進捗が`1/steps`進むごとに1回だけ`printer`へ渡す(1%刻みで届く通知で
    コンソールが埋まらないようにする)。進捗率なしの通常メッセージはそのまま渡す。"""
    last = {"step": -1}

    def _print(message: str) -> Any:
        fraction = getattr(message, "fraction", None)
        if fraction is not None:
            step = int(fraction * steps)
            if step == last["step"]:
                return None
            last["step"] = step
        return printer(message)

    return _print
