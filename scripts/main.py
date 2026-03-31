#!/usr/bin/env python3
"""
YouTube Turkish Subtitle Downloader

A production-ready tool for downloading YouTube videos with Turkish subtitles.
Designed for ASR/NLP dataset creation pipelines.

Usage:
    python main.py --input-file videos.txt --output-dir ./downloads
    python main.py --input-file videos.txt --output-dir ./downloads --allow-auto-subs
    python main.py --input-file videos.txt --output-dir ./downloads --cookies-file cookies.txt

For more options:
    python main.py --help
"""

import sys
import time
import signal
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
from threading import Event

from config import parse_args, Config
from models import VideoEntry, DownloadResult, DownloadStatus
from downloader import YTDLPDownloader
from progress_tracker import ProgressTracker, read_input_file
from logger_setup import setup_logging, get_logger


# Global shutdown event for graceful termination
shutdown_event = Event()


def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    logger = get_logger()
    logger.warning("Received interrupt signal. Finishing current downloads...")
    shutdown_event.set()


def load_video_entries(config: Config) -> List[VideoEntry]:
    """Load and parse video entries from the input file."""
    logger = get_logger()
    entries = []
    errors = 0
    
    for line_num, line in enumerate(read_input_file(config.input_file), 1):
        try:
            entry = VideoEntry.from_json_line(line)
            if not entry.video_id:
                logger.warning(f"Line {line_num}: Missing video_id, skipping")
                errors += 1
                continue
            entries.append(entry)
        except Exception as e:
            logger.warning(f"Line {line_num}: Failed to parse - {e}")
            errors += 1
    
    logger.info(f"Loaded {len(entries)} video entries ({errors} parse errors)")
    return entries


def filter_pending_entries(
    entries: List[VideoEntry],
    tracker: ProgressTracker,
    skip_completed: bool
) -> List[VideoEntry]:
    """Filter out already completed entries if skip_completed is True."""
    logger = get_logger()
    
    if not skip_completed:
        return entries
    
    pending = []
    skipped = 0
    
    for entry in entries:
        if tracker.is_completed(entry.video_id):
            skipped += 1
        else:
            pending.append(entry)
    
    if skipped > 0:
        logger.info(f"Skipping {skipped} already completed videos")
    
    return pending


def download_worker(
    entry: VideoEntry,
    downloader: YTDLPDownloader,
    tracker: ProgressTracker,
    sleep_interval: float
) -> DownloadResult:
    """Worker function for downloading a single video."""
    logger = get_logger()
    
    # Check for shutdown
    if shutdown_event.is_set():
        return DownloadResult(
            video_id=entry.video_id,
            url=entry.url,
            title=entry.title,
            duration=entry.duration,
            status=DownloadStatus.SKIPPED,
            error_message="Shutdown requested"
        )
    
    try:
        result = downloader.download_video(entry)
        tracker.record_result(result)
        
        # Rate limiting sleep
        if sleep_interval > 0 and not shutdown_event.is_set():
            time.sleep(sleep_interval)
        
        return result
        
    except Exception as e:
        logger.error(f"Worker error for {entry.video_id}: {e}")
        result = DownloadResult(
            video_id=entry.video_id,
            url=entry.url,
            title=entry.title,
            duration=entry.duration,
            status=DownloadStatus.FAILED,
            error_message=f"Worker error: {str(e)}"
        )
        tracker.record_result(result)
        return result


def run_downloads(
    entries: List[VideoEntry],
    config: Config,
    downloader: YTDLPDownloader,
    tracker: ProgressTracker
) -> Dict[str, int]:
    """
    Run downloads with concurrency control.
    
    Returns statistics dict with counts of each status.
    """
    logger = get_logger()
    stats = {
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "total": len(entries)
    }
    
    if not entries:
        logger.info("No videos to download")
        return stats
    
    logger.info(f"Starting download of {len(entries)} videos with {config.max_workers} workers")
    
    with ThreadPoolExecutor(
        max_workers=config.max_workers,
        thread_name_prefix="dl"
    ) as executor:
        # Submit all tasks
        future_to_entry = {
            executor.submit(
                download_worker,
                entry,
                downloader,
                tracker,
                config.sleep_interval
            ): entry
            for entry in entries
        }
        
        # Process completed futures
        completed = 0
        for future in as_completed(future_to_entry):
            entry = future_to_entry[future]
            completed += 1
            
            try:
                result = future.result()
                
                if result.status == DownloadStatus.SUCCESS:
                    stats["success"] += 1
                elif result.status == DownloadStatus.FAILED:
                    stats["failed"] += 1
                else:
                    stats["skipped"] += 1
                
                # Progress update
                logger.info(
                    f"Progress: {completed}/{stats['total']} "
                    f"(✓{stats['success']} ✗{stats['failed']} ⊘{stats['skipped']})"
                )
                
            except Exception as e:
                logger.error(f"Future error for {entry.video_id}: {e}")
                stats["failed"] += 1
            
            # Check for shutdown
            if shutdown_event.is_set():
                logger.warning("Shutdown requested, cancelling remaining downloads...")
                for f in future_to_entry:
                    f.cancel()
                break
    
    return stats


def print_summary(stats: Dict[str, int], config: Config) -> None:
    """Print final summary of the download session."""
    logger = get_logger()
    
    logger.info("=" * 60)
    logger.info("DOWNLOAD SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total videos:     {stats['total']}")
    logger.info(f"Successful:       {stats['success']}")
    logger.info(f"Failed:           {stats['failed']}")
    logger.info(f"Skipped:          {stats['skipped']}")
    logger.info(f"Success rate:     {stats['success']/max(stats['total'],1)*100:.1f}%")
    logger.info(f"Results log:      {config.results_log_path}")
    logger.info(f"Output directory: {config.videos_dir}")
    logger.info("=" * 60)


def main() -> int:
    """Main entry point."""
    # Parse arguments
    try:
        config = parse_args()
    except SystemExit as e:
        return e.code if e.code else 1
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Set up logging
    logger = setup_logging(config.log_level, config.output_dir)
    logger.info("YouTube Turkish Subtitle Downloader starting...")
    
    # Log configuration
    logger.info(f"Input file: {config.input_file}")
    logger.info(f"Output directory: {config.output_dir}")
    logger.info(f"Max workers: {config.max_workers}")
    logger.info(f"Allow auto subs: {config.allow_auto_subs}")
    logger.info(f"Dry run: {config.dry_run}")
    
    # Ensure directories exist
    config.ensure_directories()
    
    # Initialize components
    try:
        downloader = YTDLPDownloader(config)
    except RuntimeError as e:
        logger.error(f"Failed to initialize downloader: {e}")
        return 1
    
    tracker = ProgressTracker(config.results_log_path, config.videos_dir)
    tracker.load_state()
    
    # Load video entries
    entries = load_video_entries(config)
    if not entries:
        logger.error("No valid video entries found in input file")
        return 1
    
    # Filter already completed
    pending_entries = filter_pending_entries(
        entries, tracker, config.skip_completed
    )
    
    if not pending_entries:
        logger.info("All videos already downloaded. Nothing to do.")
        return 0
    
    # Run downloads
    stats = run_downloads(pending_entries, config, downloader, tracker)
    
    # Print summary
    print_summary(stats, config)
    
    # Return appropriate exit code
    if shutdown_event.is_set():
        logger.warning("Download interrupted by user")
        return 130  # Standard exit code for SIGINT
    
    if stats["failed"] > 0:
        logger.warning(f"{stats['failed']} videos failed to download")
        return 1 if stats["success"] == 0 else 0  # Exit 1 only if all failed
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
