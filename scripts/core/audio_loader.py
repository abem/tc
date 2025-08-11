from pathlib import Path
from typing import Optional
from scripts.core.storage_handler import GDriveStorageHandler, StorageHandler
import re

class AudioLoadError(Exception):
    pass

class AudioLoader:
    def __init__(self, storage_handler=None):
        self.storage_handler = storage_handler
        self.gdrive_handler = GDriveStorageHandler()

    def load(self, source: str) -> Path:
        """
        source: ローカルパスまたはGDrive URL/ID
        戻り値: 一時保存したローカルファイルのPath
        """
        p = Path(source)
        if p.exists():
            return p
        if re.match(r'^https://drive\.google\.com/', source):
            return self.gdrive_handler.download(source)
        raise AudioLoadError(f"未対応またはファイルが存在しません: {source}") 