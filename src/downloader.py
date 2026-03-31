"""Core download logic using yt-dlp subprocess."""

import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional, Tuple, List
import json
import re

from config import Config
from models import VideoEntry, DownloadResult, DownloadStatus, SubtitleType
from validator import PairValidator
from logger_setup import get_logger


class YTDLPDownloader:
    """
    Downloads YouTube videos with Turkish subtitles using yt-dlp.
    
    Key invariant: video + Turkish subtitle must succeed together or fail together.
    """
    
    # Error patterns that indicate access restrictions we should respect
    ACCESS_RESTRICTION_PATTERNS = [
        r"Sign in to confirm you.re not a bot",
        r"Sign in to confirm your age",
        r"This video is private",
        r"This video has been removed",
        r"Video unavailable",
        r"This video is no longer available",
        r"requires payment",
        r"rental video",
        r"members-only",
        r"Join this channel",
        r"HTTP Error 403",
        r"HTTP Error 429",  # Rate limited
        r"confirm you are not a robot",
    ]
    
    # Patterns indicating subtitle-specific issues
    NO_SUBTITLE_PATTERNS = [
        r"There are no subtitles",
        r"No subtitle.*available",
        r"Subtitles.*not available",
    ]
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger()
        self.validator = PairValidator()
        
        # Verify yt-dlp is available
        self._check_ytdlp()
    
    def _check_ytdlp(self) -> None:
        """Verify yt-dlp is installed and accessible."""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.logger.info(f"Using yt-dlp version: {result.stdout.strip()}")
            else:
                raise RuntimeError("yt-dlp check failed")
        except FileNotFoundError:
            raise RuntimeError(
                "yt-dlp not found. Install with: pip install yt-dlp"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("yt-dlp version check timed out")
    
    def download_video(self, entry: VideoEntry) -> DownloadResult:
        """
        Download a video with Turkish subtitles.
        
        Returns a DownloadResult indicating success or failure.
        The pair invariant is enforced: both video and subtitle must succeed.
        """
        video_id = entry.video_id
        url = entry.url
        
        self.logger.info(f"Starting download: {video_id} - {entry.title[:50]}...")
        
        # Create temp directory for this download
        temp_dir = self.config.temp_dir / video_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Build yt-dlp command
            cmd = self._build_ytdlp_command(entry, temp_dir)
            
            if self.config.dry_run:
                self.logger.info(f"[DRY RUN] Would execute: {' '.join(cmd)}")
                return DownloadResult(
                    video_id=video_id,
                    url=url,
                    title=entry.title,
                    duration=entry.duration,
                    status=DownloadStatus.SKIPPED,
                    error_message="Dry run mode - no download performed"
                )
            
            # Execute download
            success, error_msg = self._execute_download(cmd, video_id)
            
            if not success:
                self._cleanup_temp(temp_dir)
                return DownloadResult(
                    video_id=video_id,
                    url=url,
                    title=entry.title,
                    duration=entry.duration,
                    status=DownloadStatus.FAILED,
                    error_message=error_msg
                )
            
            # Validate the downloaded pair
            is_valid, video_path, subtitle_path, subtitle_type, validation_error = \
                self.validator.validate_pair(video_id, temp_dir)
            
            # Check if auto-generated subs are allowed
            if is_valid and subtitle_type == SubtitleType.AUTO_GENERATED:
                if not self.config.allow_auto_subs:
                    is_valid = False
                    validation_error = "Only auto-generated subtitles available (use --allow-auto-subs to accept)"
            
            if not is_valid:
                self.logger.warning(f"Pair validation failed for {video_id}: {validation_error}")
                self._handle_failed_download(temp_dir, video_path, subtitle_path)
                return DownloadResult(
                    video_id=video_id,
                    url=url,
                    title=entry.title,
                    duration=entry.duration,
                    status=DownloadStatus.FAILED,
                    error_message=validation_error
                )
            
            # Move successful files to final destination
            final_video_path, final_subtitle_path = self._move_to_final(
                video_id, video_path, subtitle_path
            )
            
            # Cleanup temp directory
            self._cleanup_temp(temp_dir)
            
            self.logger.info(f"Successfully downloaded: {video_id}")
            
            return DownloadResult(
                video_id=video_id,
                url=url,
                title=entry.title,
                duration=entry.duration,
                status=DownloadStatus.SUCCESS,
                video_path=final_video_path,
                subtitle_path=final_subtitle_path,
                subtitle_type=subtitle_type,
            )
            
        except Exception as e:
            self.logger.error(f"Unexpected error downloading {video_id}: {e}")
            self._cleanup_temp(temp_dir)
            return DownloadResult(
                video_id=video_id,
                url=url,
                title=entry.title,
                duration=entry.duration,
                status=DownloadStatus.FAILED,
                error_message=f"Unexpected error: {str(e)}"
            )
    
    def _build_ytdlp_command(self, entry: VideoEntry, output_dir: Path) -> List[str]:
        """Build the yt-dlp command with appropriate options."""
        cmd = [
            "yt-dlp",
            "--no-playlist",  # Don't download playlists
            "--no-overwrites",  # Don't overwrite existing files
            
            # Video format
            "-f", self.config.video_format,
            "--merge-output-format", self.config.merge_output_format,
            
            # Subtitles - Turkish only
            "--write-subs",
            "--sub-langs", "tr",
            "--sub-format", self.config.subtitle_format,
            
            # Output template - use video_id as filename
            "-o", str(output_dir / "%(id)s.%(ext)s"),
            
            # Metadata
            "--no-write-info-json",  # We track our own metadata
            "--no-write-description",
            "--no-write-thumbnail",
            
            # Progress
            "--progress",
            "--newline",  # Better for parsing output
            
            # Error handling
            "--no-abort-on-error",
            "--ignore-errors",
            
            # Respect restrictions
            "--no-check-certificate",  # Some CDNs have cert issues
        ]
        
        # Prefer manual subtitles over auto-generated
        if not self.config.allow_auto_subs:
            cmd.extend(["--no-write-auto-subs"])
        else:
            # Write auto-subs only as fallback
            cmd.extend(["--write-auto-subs"])
        
        # Cookies file for authentication
        if self.config.cookies_file:
            cmd.extend(["--cookies", str(self.config.cookies_file)])
        
        # Rate limiting
        if self.config.rate_limit:
            cmd.extend(["--limit-rate", self.config.rate_limit])
        
        # Retries
        cmd.extend(["--retries", str(self.config.max_retries)])
        
        # Add the URL
        cmd.append(entry.url)
        
        return cmd
    
    def _execute_download(self, cmd: List[str], video_id: str) -> Tuple[bool, Optional[str]]:
        """
        Execute the yt-dlp download command.
        
        Returns:
            Tuple of (success, error_message)
        """
        self.logger.debug(f"Executing: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout for long videos
            )
            
            output = result.stdout + result.stderr
            
            # Check for access restrictions
            for pattern in self.ACCESS_RESTRICTION_PATTERNS:
                if re.search(pattern, output, re.IGNORECASE):
                    self.logger.warning(f"Access restriction detected for {video_id}")
                    return False, f"Access restricted: {pattern}"
            
            # Check for subtitle-specific issues (still want to check video download)
            for pattern in self.NO_SUBTITLE_PATTERNS:
                if re.search(pattern, output, re.IGNORECASE):
                    self.logger.warning(f"No Turkish subtitles for {video_id}")
                    return False, "No Turkish subtitles available"
            
            if result.returncode != 0:
                # Extract meaningful error message
                error_lines = [
                    line for line in output.split("\n")
                    if "ERROR" in line or "error" in line.lower()
                ]
                error_msg = error_lines[0] if error_lines else f"yt-dlp exit code: {result.returncode}"
                return False, error_msg
            
            return True, None
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Download timed out for {video_id}")
            return False, "Download timed out (exceeded 1 hour)"
        except Exception as e:
            self.logger.error(f"Download execution error for {video_id}: {e}")
            return False, str(e)
    
    def _handle_failed_download(
        self,
        temp_dir: Path,
        video_path: Optional[Path],
        subtitle_path: Optional[Path]
    ) -> None:
        """Handle cleanup for a failed download."""
        if self.config.delete_failed_files:
            self.validator.cleanup_failed_files(
                video_path, subtitle_path, delete=True
            )
        else:
            self.validator.cleanup_failed_files(
                video_path, subtitle_path,
                delete=False,
                failed_dir=self.config.failed_dir
            )
        self._cleanup_temp(temp_dir)
    
    def _move_to_final(
        self,
        video_id: str,
        video_path: Path,
        subtitle_path: Path
    ) -> Tuple[Path, Path]:
        """Move validated files to the final destination directory."""
        final_video = self.config.videos_dir / video_path.name
        final_subtitle = self.config.videos_dir / subtitle_path.name
        
        # Move files
        shutil.move(str(video_path), str(final_video))
        shutil.move(str(subtitle_path), str(final_subtitle))
        
        return final_video, final_subtitle
    
    def _cleanup_temp(self, temp_dir: Path) -> None:
        """Remove temporary directory and its contents."""
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
        except IOError as e:
            self.logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")


def check_subtitle_availability(
    url: str,
    cookies_file: Optional[Path] = None
) -> Tuple[bool, bool, str]:
    """
    Check if Turkish subtitles are available for a video without downloading.
    
    Returns:
        Tuple of (has_manual_turkish, has_auto_turkish, error_or_info)
    """
    logger = get_logger()
    
    cmd = [
        "yt-dlp",
        "--list-subs",
        "--no-download",
        "--skip-download",
        url
    ]
    
    if cookies_file:
        cmd.extend(["--cookies", str(cookies_file)])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        output = result.stdout + result.stderr
        
        # Parse subtitle listing
        has_manual_tr = False
        has_auto_tr = False
        
        # Look for Turkish in manual subtitles section
        if re.search(r"Available subtitles.*\btr\b", output, re.DOTALL | re.IGNORECASE):
            has_manual_tr = True
        
        # Look for Turkish in auto-generated section
        if re.search(r"Available automatic captions.*\btr\b", output, re.DOTALL | re.IGNORECASE):
            has_auto_tr = True
        
        if has_manual_tr:
            return True, has_auto_tr, "Manual Turkish subtitles available"
        elif has_auto_tr:
            return False, True, "Only auto-generated Turkish subtitles available"
        else:
            return False, False, "No Turkish subtitles available"
            
    except subprocess.TimeoutExpired:
        return False, False, "Timeout checking subtitles"
    except Exception as e:
        logger.error(f"Error checking subtitles: {e}")
        return False, False, str(e)
