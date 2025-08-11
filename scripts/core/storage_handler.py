from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

class StorageHandler(ABC):
    @abstractmethod
    def download(self, file_id_or_path: str) -> Path:
        pass

    @abstractmethod
    def upload(self, file_path: Path, parent_id: Optional[str] = None) -> Optional[str]:
        pass

# Google Drive対応
import tempfile
from gdrive_handler import GDriveHandler

class GDriveStorageHandler(StorageHandler):
    def __init__(self):
        self.gdrive = GDriveHandler()

    def download(self, file_id_or_url: str) -> Path:
        # file_id_or_urlがURLならID抽出
        import re
        m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', file_id_or_url)
        file_id = m.group(1) if m else file_id_or_url
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
            self.gdrive.download_file(file_id, tmp.name)
            return Path(tmp.name)

    def upload(self, file_path: Path, parent_id: Optional[str] = None) -> Optional[str]:
        return self.gdrive.upload_file(file_content=str(file_path), filename=file_path.name, parent_id=parent_id) 