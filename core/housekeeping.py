"""WebUI の作業領域の整理(output/uploads、output/queue_downloads)。

- output/uploads: アップロードされたファイル。文字起こしの後も残る(履歴が元ファイルのパスを記録する
  ため、処理直後には消さない)。放置すると増え続けるので、一定日数を過ぎたものだけを消す。
- output/queue_downloads/<トークン>/: URL入力のダウンロード。処理後の音声は消えるが、空のディレクトリや
  失敗時の部分ファイル(.part など)が残る。
"""

import shutil
import time
from pathlib import Path
from typing import Iterable, List, Optional

from core.logging import get_logger

logger = get_logger(__name__)

# 1 日未満の保持期間は拒否する(投入直後・処理中のファイルを消す事故を構造的に防ぐ)。
MIN_RETENTION_DAYS = 1
SECONDS_PER_DAY = 86400


def cleanup_old_entries(
    directory: Path,
    max_age_days: float,
    *,
    protected_paths: Iterable[Path] = (),
    now: Optional[float] = None,
) -> List[str]:
    """`directory`直下で、更新から`max_age_days`日を過ぎた項目(サブディレクトリ、および
    平置きファイル)を削除し、削除した項目名のリストを返す。

    - `protected_paths`(処理待ち・処理中のジョブが使うファイル)を含む項目は、古くても消さない。
    - シンボリックリンクは辿らず、消さない(リンク先を巻き込まない)。
    - 1 件の削除に失敗しても警告だけにして、残りの整理を続ける。
    - 保持期間が`MIN_RETENTION_DAYS`未満なら`ValueError`(全削除の事故を防ぐ)。
    """
    if max_age_days < MIN_RETENTION_DAYS:
        raise ValueError(f"保持期間は{MIN_RETENTION_DAYS}日以上にしてください: {max_age_days}")
    directory = Path(directory)
    if not directory.is_dir():
        return []

    cutoff = (time.time() if now is None else now) - max_age_days * SECONDS_PER_DAY
    protected = []
    for p in protected_paths:
        try:
            protected.append(Path(p).resolve())
        except OSError:
            continue

    removed: List[str] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_symlink():
            continue
        try:
            if entry.stat().st_mtime > cutoff:
                continue
            resolved = entry.resolve()
            if any(p == resolved or resolved in p.parents for p in protected):
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError as e:
            logger.warning("古い項目の整理に失敗(スキップ): %s: %s", entry, e)
            continue
        removed.append(entry.name)
    if removed:
        logger.info("%s の古い項目を%d件削除しました(保持期間%s日)", directory, len(removed), max_age_days)
    return removed
