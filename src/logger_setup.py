"""Logging configuration for the YouTube Turkish subtitle downloader."""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(log_level: str = "INFO", output_dir: Path = None) -> logging.Logger:
    """
    Set up logging with both console and file handlers.
    
    Args:
        log_level: The logging level (DEBUG, INFO, WARNING, ERROR)
        output_dir: Directory for log files (optional)
    
    Returns:
        The configured root logger
    """
    # Create logger
    logger = logging.getLogger("yt_tr_downloader")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Format for console - simpler, with thread name for concurrent downloads
    console_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler if output_dir provided
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        log_filename = f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(
            output_dir / log_filename,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        
        # More detailed format for file
        file_format = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(threadName)s] [%(funcName)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger


def get_logger() -> logging.Logger:
    """Get the application logger."""
    return logging.getLogger("yt_tr_downloader")
