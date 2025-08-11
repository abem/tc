from pathlib import Path
from typing import Optional, Union, Any, Generator
import logging
import shutil
import tempfile
import os

class FileUtils:
    """ファイル操作に関するユーティリティクラス"""
    
    @staticmethod
    def convert_file_size(size: Optional[Union[str, int, float]]) -> Optional[int]:
        """ファイルサイズを整数に変換"""
        if size is None:
            return None
        try:
            if not isinstance(size, int):
                if isinstance(size, str):
                    size = int(float(size.strip()))
                else:
                    size = int(float(size))
            if size < 0:
                logging.warning(f"不正なファイルサイズ: {size}")
                return None
            return size
        except (ValueError, TypeError) as e:
            logging.warning(f"ファイルサイズ変換エラー: {e}")
            return None

    @staticmethod
    @contextmanager
    def temp_file_context(prefix: str = "temp_", suffix: str = ".tmp") -> Generator[Path, None, None]:
        """一時ファイルのコンテキストマネージャ
        
        Args:
            prefix (str): ファイル名の接頭辞
            suffix (str): ファイル名の接尾辞
            
        Yields:
            Path: 一時ファイルのパス
        """
        temp_path = None
        try:
            temp_path = Path(tempfile.mktemp(prefix=prefix, suffix=suffix))
            yield temp_path
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as e:
                    logging.warning(f"一時ファイルの削除に失敗しました: {e}")
    
    @staticmethod
    def get_temp_dir() -> Path:
        """一時ディレクトリのパスを取得
        
        Returns:
            Path: 一時ディレクトリのパス
        """
        return Path(tempfile.gettempdir())
    
    @staticmethod
    def create_temp_dir(prefix: str = "temp_") -> Path:
        """一時ディレクトリを作成
        
        Args:
            prefix (str): ディレクトリ名の接頭辞
            
        Returns:
            Path: 作成した一時ディレクトリのパス
        """
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        return temp_dir
    
    @staticmethod
    def remove_temp_dir(temp_dir: Path) -> None:
        """一時ディレクトリを削除
        
        Args:
            temp_dir (Path): 削除する一時ディレクトリのパス
        """
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logging.warning(f"一時ディレクトリの削除に失敗しました: {e}")
    
    @staticmethod
    def get_unique_filename(base_name: str, directory: Path) -> Path:
        """一意のファイル名を生成
        
        Args:
            base_name (str): 基本ファイル名
            directory (Path): 保存先ディレクトリ
            
        Returns:
            Path: 一意のファイルパス
        """
        counter = 1
        name, ext = os.path.splitext(base_name)
        while True:
            new_name = f"{name}_{counter}{ext}" if counter > 1 else f"{name}{ext}"
            new_path = directory / new_name
            if not new_path.exists():
                return new_path
            counter += 1
