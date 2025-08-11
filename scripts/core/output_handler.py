from pathlib import Path
from typing import Optional

class OutputHandler:
    def __init__(self, storage_handler=None):
        self.storage_handler = storage_handler

    def save(self, content: str, output_path: Path, output_format: str = 'txt') -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def upload(self, file_path: Path, parent_id: Optional[str] = None, original_audio_gdrive_id: Optional[str] = None) -> Optional[dict]:
        """
        Google Drive等へのアップロード処理
        """
        if self.storage_handler is None:
            raise NotImplementedError("OutputHandler.upload()はstorage_handler未設定のため未実装です")
        # mp3のGDrive IDから親フォルダIDを取得
        gdrive = self.storage_handler.gdrive if hasattr(self.storage_handler, 'gdrive') else None
        if original_audio_gdrive_id and gdrive:
            parent_id = gdrive.get_parent_folder_id(original_audio_gdrive_id)
        file_id = self.storage_handler.upload(file_path, parent_id=parent_id)
        folder_id = gdrive.get_parent_folder_id(file_id) if gdrive else None
        folder_path = gdrive.get_file_path(file_id) if gdrive else None
        file_url = gdrive.get_file_url(file_id) if gdrive else None
        folder_url = f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else None
        return {
            'file_id': file_id,
            'file_url': file_url,
            'folder_id': folder_id,
            'folder_path': folder_path,
            'folder_url': folder_url
        } 