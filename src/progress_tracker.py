"""Progress tracking and resume functionality."""

import json
import fcntl
from pathlib import Path
from typing import Dict, Set, Optional, Iterator
from dataclasses import dataclass

from models import DownloadResult, DownloadStatus, SubtitleType
from logger_setup import get_logger


@dataclass
class ProgressState:
    """Current progress state."""
    completed_ids: Set[str]
    failed_ids: Set[str]
    results: Dict[str, DownloadResult]


class ProgressTracker:
    """
    Tracks download progress and enables resume functionality.
    
    Uses a JSONL file to persist results, with file locking for
    concurrent access safety.
    """
    
    def __init__(self, results_log_path: Path, videos_dir: Path):
        """
        Initialize the progress tracker.
        
        Args:
            results_log_path: Path to the JSONL results log file
            videos_dir: Directory where successful downloads are stored
        """
        self.results_log_path = results_log_path
        self.videos_dir = videos_dir
        self.logger = get_logger()
        self._state: Optional[ProgressState] = None
    
    def load_state(self) -> ProgressState:
        """Load the current progress state from the results log."""
        completed_ids: Set[str] = set()
        failed_ids: Set[str] = set()
        results: Dict[str, DownloadResult] = {}
        
        if self.results_log_path.exists():
            try:
                with open(self.results_log_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            result = DownloadResult.from_json_line(line)
                            results[result.video_id] = result
                            
                            if result.status == DownloadStatus.SUCCESS:
                                completed_ids.add(result.video_id)
                            elif result.status == DownloadStatus.FAILED:
                                failed_ids.add(result.video_id)
                        except (json.JSONDecodeError, KeyError) as e:
                            self.logger.warning(f"Failed to parse results log line {line_num}: {e}")
            except IOError as e:
                self.logger.error(f"Failed to read results log: {e}")
        
        self._state = ProgressState(
            completed_ids=completed_ids,
            failed_ids=failed_ids,
            results=results
        )
        
        self.logger.info(
            f"Loaded progress state: {len(completed_ids)} completed, "
            f"{len(failed_ids)} failed"
        )
        
        return self._state
    
    def is_completed(self, video_id: str) -> bool:
        """
        Check if a video was previously completed successfully.
        
        Also verifies that the files still exist on disk.
        """
        if self._state is None:
            self.load_state()
        
        if video_id not in self._state.completed_ids:
            return False
        
        # Verify files still exist
        result = self._state.results.get(video_id)
        if result and result.video_path and result.subtitle_path:
            video_exists = Path(result.video_path).exists()
            subtitle_exists = Path(result.subtitle_path).exists()
            
            if video_exists and subtitle_exists:
                return True
            else:
                self.logger.warning(
                    f"Video {video_id} marked as complete but files missing "
                    f"(video: {video_exists}, subtitle: {subtitle_exists})"
                )
                # Remove from completed set since files are missing
                self._state.completed_ids.discard(video_id)
                return False
        
        return False
    
    def record_result(self, result: DownloadResult) -> None:
        """
        Record a download result to the log file.
        
        Uses file locking for concurrent access safety.
        """
        # Append to log file with locking
        try:
            with open(self.results_log_path, "a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(result.to_json_line() + "\n")
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except IOError as e:
            self.logger.error(f"Failed to write result for {result.video_id}: {e}")
            return
        
        # Update in-memory state
        if self._state is None:
            self._state = ProgressState(set(), set(), {})
        
        self._state.results[result.video_id] = result
        
        if result.status == DownloadStatus.SUCCESS:
            self._state.completed_ids.add(result.video_id)
            self._state.failed_ids.discard(result.video_id)
        elif result.status == DownloadStatus.FAILED:
            self._state.failed_ids.add(result.video_id)
            self._state.completed_ids.discard(result.video_id)
    
    def get_stats(self) -> Dict[str, int]:
        """Get current statistics."""
        if self._state is None:
            self.load_state()
        
        return {
            "completed": len(self._state.completed_ids),
            "failed": len(self._state.failed_ids),
            "total_recorded": len(self._state.results),
        }
    
    def find_video_files(self, video_id: str) -> tuple[Optional[Path], Optional[Path]]:
        """
        Find existing video and subtitle files for a video ID.
        
        Returns:
            Tuple of (video_path, subtitle_path), either may be None
        """
        video_path = None
        subtitle_path = None
        
        # Common video extensions
        video_extensions = [".mp4", ".mkv", ".webm", ".m4v"]
        # Common subtitle extensions
        subtitle_extensions = [".tr.srt", ".tr.vtt", ".srt", ".vtt"]
        
        for ext in video_extensions:
            candidate = self.videos_dir / f"{video_id}{ext}"
            if candidate.exists() and candidate.stat().st_size > 0:
                video_path = candidate
                break
        
        for ext in subtitle_extensions:
            candidate = self.videos_dir / f"{video_id}{ext}"
            if candidate.exists() and candidate.stat().st_size > 0:
                subtitle_path = candidate
                break
        
        return video_path, subtitle_path


def read_input_file(input_path: Path) -> Iterator[str]:
    """
    Read the input file and yield valid JSON lines.
    
    Skips empty lines and logs parsing warnings.
    """
    logger = get_logger()
    
    with open(input_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            # Quick validation that it looks like JSON
            if not line.startswith("{"):
                logger.warning(f"Line {line_num} does not appear to be JSON, skipping")
                continue
            
            yield line
