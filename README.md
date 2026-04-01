# YouTube Downloader

Download YouTube videos with Turkish subtitles at scale. Built for acquiring speech and language data, with support for cookies, auto-retry, and concurrent downloads.

## Features

- Turkish subtitle extraction
- Concurrent downloads (configurable worker count)
- Graceful interrupt handling
- Cookie/authentication support
- Detailed progress tracking
- Auto-caption fallback
- Structured error reporting

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

## Usage

Download from a list of video URLs:

```bash
python scripts/main.py --input-file videos.txt --output-dir ./downloads
```

With optional Turkish subtitles and auto-captions:

```bash
python scripts/main.py \
  --input-file videos.txt \
  --output-dir ./downloads \
  --allow-auto-subs \
  --workers 4
```

Input file format: One video ID or URL per line.

## Configuration

Edit `.env` to set:
- `YT_COOKIES_FILE` - Browser cookies export
- `WORKER_COUNT` - Concurrent downloads
- `TIMEOUT` - Download timeout in seconds
