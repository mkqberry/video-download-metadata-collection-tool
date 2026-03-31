"""Data models for the YouTube Turkish subtitle downloader."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import json


class DownloadStatus(str, Enum):
    """Status of a download attempt."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # Already downloaded
    PENDING = "pending"


class SubtitleType(str, Enum):
    """Type of subtitle downloaded."""
    MANUAL = "manual"
    AUTO_GENERATED = "auto_generated"
    NONE = "none"


@dataclass
class VideoEntry:
    """Represents a video entry from the input file."""
    video_id: str
    url: str
    title: str
    duration: float
    channel: str
    filter_reason: str = ""
    found_at: str = ""
    
    # Additional fields that might be present
    extra_data: dict = field(default_factory=dict)
    
    @classmethod
    def from_json_line(cls, line: str) -> "VideoEntry":
        """Parse a JSON line into a VideoEntry."""
        data = json.loads(line.strip())
        
        # Extract known fields
        video_id = data.pop("video_id", "")
        url = data.pop("url", "")
        title = data.pop("title", "")
        duration = float(data.pop("duration", 0))
        channel = data.pop("channel", "")
        filter_reason = data.pop("filter_reason", "")
        found_at = data.pop("found_at", "")
        
        # If video_id not present, extract from URL
        if not video_id and url:
            if "watch?v=" in url:
                video_id = url.split("watch?v=")[-1].split("&")[0]
            elif "youtu.be/" in url:
                video_id = url.split("youtu.be/")[-1].split("?")[0]
        
        return cls(
            video_id=video_id,
            url=url,
            title=title,
            duration=duration,
            channel=channel,
            filter_reason=filter_reason,
            found_at=found_at,
            extra_data=data  # Remaining fields
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {
            "video_id": self.video_id,
            "url": self.url,
            "title": self.title,
            "duration": self.duration,
            "channel": self.channel,
            "filter_reason": self.filter_reason,
            "found_at": self.found_at,
        }
        result.update(self.extra_data)
        return result


@dataclass
class DownloadResult:
    """Result of a download attempt."""
    video_id: str
    url: str
    title: str
    duration: float
    status: DownloadStatus
    video_path: Optional[Path] = None
    subtitle_path: Optional[Path] = None
    subtitle_type: SubtitleType = SubtitleType.NONE
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_json_line(self) -> str:
        """Serialize to a JSON line for logging."""
        data = {
            "video_id": self.video_id,
            "url": self.url,
            "title": self.title,
            "duration": self.duration,
            "status": self.status.value,
            "video_path": str(self.video_path) if self.video_path else None,
            "subtitle_path": str(self.subtitle_path) if self.subtitle_path else None,
            "subtitle_type": self.subtitle_type.value,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
        }
        return json.dumps(data, ensure_ascii=False)
    
    @classmethod
    def from_json_line(cls, line: str) -> "DownloadResult":
        """Parse a JSON line into a DownloadResult."""
        data = json.loads(line.strip())
        return cls(
            video_id=data["video_id"],
            url=data["url"],
            title=data["title"],
            duration=data["duration"],
            status=DownloadStatus(data["status"]),
            video_path=Path(data["video_path"]) if data.get("video_path") else None,
            subtitle_path=Path(data["subtitle_path"]) if data.get("subtitle_path") else None,
            subtitle_type=SubtitleType(data.get("subtitle_type", "none")),
            error_message=data.get("error_message"),
            timestamp=data.get("timestamp", ""),
        )
    
    @property
    def is_success(self) -> bool:
        """Check if this result represents a successful download."""
        return self.status == DownloadStatus.SUCCESS
