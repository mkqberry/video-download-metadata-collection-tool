"""Configuration handling for the YouTube Turkish subtitle downloader."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import argparse


@dataclass
class Config:
    """Configuration for the downloader."""
    
    # Required paths
    input_file: Path
    output_dir: Path
    
    # Optional paths
    cookies_file: Optional[Path] = None
    
    # Download options
    max_workers: int = 4
    allow_auto_subs: bool = False
    dry_run: bool = False
    
    # Cleanup options
    delete_failed_files: bool = True
    
    # Video format options - flexible fallback chain
    video_format: str = "bestvideo+bestaudio/best"
    merge_output_format: str = "mkv"  # mkv supports all codecs without re-encoding
    
    # Subtitle options
    subtitle_format: str = "srt"  # or "vtt"
    
    # Rate limiting (be respectful)
    rate_limit: Optional[str] = None  # e.g., "50K" for 50KB/s
    sleep_interval: float = 1.0  # seconds between downloads
    
    # Retry settings
    max_retries: int = 3
    retry_delay: float = 5.0
    
    # Resume settings
    skip_completed: bool = True
    
    # Logging
    log_level: str = "INFO"
    results_log_name: str = "download_results.jsonl"
    
    def __post_init__(self):
        """Validate and normalize paths."""
        self.input_file = Path(self.input_file).resolve()
        self.output_dir = Path(self.output_dir).resolve()
        
        if self.cookies_file:
            self.cookies_file = Path(self.cookies_file).resolve()
    
    @property
    def results_log_path(self) -> Path:
        """Path to the results log file."""
        return self.output_dir / self.results_log_name
    
    @property
    def videos_dir(self) -> Path:
        """Directory for successful video downloads."""
        return self.output_dir / "videos"
    
    @property
    def failed_dir(self) -> Path:
        """Directory for failed/partial downloads (if not deleting)."""
        return self.output_dir / "failed"
    
    @property
    def temp_dir(self) -> Path:
        """Temporary directory for in-progress downloads."""
        return self.output_dir / ".temp"
    
    def ensure_directories(self) -> None:
        """Create necessary directories."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        if not self.delete_failed_files:
            self.failed_dir.mkdir(parents=True, exist_ok=True)


def parse_args() -> Config:
    """Parse command-line arguments and return a Config object."""
    parser = argparse.ArgumentParser(
        description="Download YouTube videos with Turkish subtitles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input-file videos.txt --output-dir ./downloads
  %(prog)s --input-file videos.txt --output-dir ./downloads --cookies-file cookies.txt
  %(prog)s --input-file videos.txt --output-dir ./downloads --max-workers 8 --allow-auto-subs
  %(prog)s --input-file videos.txt --output-dir ./downloads --dry-run
        """
    )
    
    # Required arguments
    parser.add_argument(
        "--input-file", "-i",
        type=Path,
        required=True,
        help="Path to the text file with JSON lines (one video per line)"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        required=True,
        help="Root directory for downloaded videos and subtitles"
    )
    
    # Optional path arguments
    parser.add_argument(
        "--cookies-file", "-c",
        type=Path,
        default=None,
        help="Path to cookies.txt file for authenticated requests (Netscape format)"
    )
    
    # Download options
    parser.add_argument(
        "--max-workers", "-w",
        type=int,
        default=4,
        help="Maximum number of concurrent downloads (default: 4)"
    )
    
    parser.add_argument(
        "--allow-auto-subs",
        action="store_true",
        default=False,
        help="Allow auto-generated Turkish subtitles if manual ones are not available"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Parse and plan downloads without actually downloading"
    )
    
    # Cleanup options
    parser.add_argument(
        "--keep-failed-files",
        action="store_true",
        default=False,
        help="Keep partial/failed files instead of deleting them"
    )
    
    # Format options
    parser.add_argument(
        "--subtitle-format",
        choices=["srt", "vtt"],
        default="srt",
        help="Subtitle file format (default: srt)"
    )
    
    parser.add_argument(
        "--video-format",
        type=str,
        default="bestvideo+bestaudio/best",
        help="yt-dlp video format string (default: bestvideo+bestaudio/best)"
    )
    
    parser.add_argument(
        "--merge-format",
        choices=["mkv", "mp4", "webm"],
        default="mkv",
        help="Output container format (default: mkv, most compatible)"
    )
    
    # Rate limiting
    parser.add_argument(
        "--rate-limit",
        type=str,
        default=None,
        help="Rate limit for downloads (e.g., '50K' for 50KB/s)"
    )
    
    parser.add_argument(
        "--sleep-interval",
        type=float,
        default=1.0,
        help="Seconds to sleep between downloads (default: 1.0)"
    )
    
    # Resume options
    parser.add_argument(
        "--force-redownload",
        action="store_true",
        default=False,
        help="Re-download even if files already exist"
    )
    
    # Logging options
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Validate input file exists
    if not args.input_file.exists():
        parser.error(f"Input file does not exist: {args.input_file}")
    
    if args.cookies_file and not args.cookies_file.exists():
        parser.error(f"Cookies file does not exist: {args.cookies_file}")
    
    return Config(
        input_file=args.input_file,
        output_dir=args.output_dir,
        cookies_file=args.cookies_file,
        max_workers=args.max_workers,
        allow_auto_subs=args.allow_auto_subs,
        dry_run=args.dry_run,
        delete_failed_files=not args.keep_failed_files,
        subtitle_format=args.subtitle_format,
        video_format=args.video_format,
        merge_output_format=args.merge_format,
        rate_limit=args.rate_limit,
        sleep_interval=args.sleep_interval,
        skip_completed=not args.force_redownload,
        log_level=args.log_level,
    )
