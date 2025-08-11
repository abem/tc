import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime

class Logger:
    """ログ出力を担当するクラス"""
    
    @staticmethod
    def setup_logger(
        log_level: str,
        log_file: str,
        log_format: str
    ) -> logging.Logger:
        """ロガーの設定を行う
        
        Args:
            log_level (str): ログレベル（'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'）
            log_file (str): ログファイルのパス
            log_format (str): ログのフォーマット
            
        Returns:
            logging.Logger: 設定済みのロガー
            
        Raises:
            ValueError: 不正なログレベルが指定された場合
        """
        # ログレベルの設定
        level = getattr(logging, log_level.upper(), None)
        if not isinstance(level, int):
            raise ValueError(f"不正なログレベル: {log_level}")
        
        # ルートロガーの設定
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        
        # 既存のハンドラをクリア
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # コンソール出力の設定
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(log_format))
        root_logger.addHandler(console_handler)
        
        # ファイル出力の設定
        if log_file:
            # ログディレクトリの作成
            log_dir = Path(log_file).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # ファイルハンドラの設定
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(logging.Formatter(log_format))
            root_logger.addHandler(file_handler)
        
        return root_logger
    
    @staticmethod
    def log_progress(message: str, level: str = "INFO") -> None:
        """進捗ログを出力する
        
        Args:
            message (str): ログメッセージ
            level (str): ログレベル
            
        Raises:
            ValueError: 不正なログレベルが指定された場合
        """
        logger = logging.getLogger(__name__)
        log_level = getattr(logging, level.upper(), None)
        
        if not isinstance(log_level, int):
            raise ValueError(f"不正なログレベル: {level}")
        
        logger.log(log_level, message)
    
    @staticmethod
    def log_error(error: Exception, include_traceback: bool = True) -> None:
        """エラーログを出力する
        
        Args:
            error (Exception): エラーオブジェクト
            include_traceback (bool): トレースバックを含めるかどうか
        """
        logger = logging.getLogger(__name__)
        
        if include_traceback:
            logger.exception(f"エラーが発生: {str(error)}")
        else:
            logger.error(f"エラーが発生: {str(error)}")
    
    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """指定された名前のロガーを取得する
        
        Args:
            name (str): ロガーの名前
            
        Returns:
            logging.Logger: ロガー
        """
        return logging.getLogger(name)
    
    @staticmethod
    def set_log_level(logger: logging.Logger, level: str) -> None:
        """ロガーのログレベルを設定する
        
        Args:
            logger (logging.Logger): ロガー
            level (str): ログレベル
            
        Raises:
            ValueError: 不正なログレベルが指定された場合
        """
        log_level = getattr(logging, level.upper(), None)
        if not isinstance(log_level, int):
            raise ValueError(f"不正なログレベル: {level}")
        
        logger.setLevel(log_level)

# グローバルロガーの作成
logger = Logger.get_logger(__name__) 