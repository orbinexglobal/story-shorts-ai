"""
Channel stats snapshot: subscribers, views, video count via the Data API.

Read-only. Run locally (or anywhere the YOUTUBE_* env vars are set) to grab a
point-in-time snapshot of the channel, e.g. to measure a week of shipping:

    python scripts/channel_stats.py

Needs the youtube.readonly scope, which the normal upload token already has.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))

    try:
        from googleapiclient.discovery import build
        from youtube.auth import get_credentials
        from youtube.uploader import check_youtube_credentials
    except ImportError as exc:
        print(f"google-api-python-client not installed: {exc}", file=sys.stderr)
        sys.exit(1)

    check_youtube_credentials()

    youtube = build("youtube", "v3", credentials=get_credentials())
    channel = youtube.channels().list(part="statistics,snippet", mine=True).execute()["items"][0]
    stats = channel["statistics"]

    print(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print(f"Channel:      {channel['snippet']['title']}")
    print(f"Subscribers:  {stats.get('subscriberCount', '0')}")
    print(f"Total views:  {stats.get('viewCount', '0')}")
    print(f"Videos:       {stats.get('videoCount', '0')}")


if __name__ == "__main__":
    main()