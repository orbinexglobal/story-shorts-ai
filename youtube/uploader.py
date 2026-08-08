"""Upload the rendered Short to YouTube via the Data API v3."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from config.logging_setup import get_logger
from config.settings import Config
from providers.base import ProviderError
from youtube.auth import get_credentials

logger = get_logger(__name__)


def _build_client():
    """Lazily import and build a YouTube Data API client."""
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ProviderError(
            "google-api-python-client is not installed. Run "
            "`pip install -r requirements.txt`."
        ) from exc
    return build("youtube", "v3", credentials=get_credentials())


def count_uploads_today(cfg: Config) -> int:
    """
    Count Shorts published to the channel today (UTC).

    Used to enforce the daily upload target across multiple scheduled runs.
    Uses `playlistItems.list` on the channel's uploads playlist, which is
    reverse-chronological, so we stop scanning once we pass today.

    Requires the OAuth scope to include youtube.readonly (plus youtube.upload);
    see SETUP.md / scripts/get_youtube_refresh_token.py.

    Returns:
        Number of videos in the uploads playlist published today (UTC).

    Raises:
        ProviderError: if authentication or the list call fails.
    """
    youtube = _build_client()

    channels = youtube.channels().list(part="contentDetails", mine=True).execute()
    try:
        uploads_playlist = channels["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except (KeyError, IndexError) as exc:
        raise ProviderError(f"Could not resolve uploads playlist: {channels}") from exc

    today = datetime.now(timezone.utc).date()
    count = 0
    page_token = None
    while True:
        response = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            published = item.get("contentDetails", {}).get("videoPublishedAt")
            if not published:
                continue
            published_date = datetime.fromisoformat(published.replace("Z", "+00:00")).date()
            if published_date == today:
                count += 1
            elif published_date < today:
                return count  # playlist is newest-first; today's window is over
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return count


def upload_video(
    video_path: Path, *, title: str, description: str, tags: list[str], cfg: Config
) -> str:
    """
    Upload `video_path` to YouTube as a Short.

    Returns:
        The uploaded video's YouTube ID.

    Raises:
        ProviderError: if authentication or upload fails.
    """
    from googleapiclient.http import MediaFileUpload

    youtube = _build_client()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": cfg.youtube.category_id,
            "defaultLanguage": cfg.youtube.default_language,
        },
        "status": {
            "privacyStatus": cfg.youtube.visibility,
            "selfDeclaredMadeForKids": cfg.youtube.made_for_kids,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)

    try:
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("Upload progress: %d%%", int(status.progress() * 100))
        video_id = response["id"]
        logger.info("Uploaded video: https://youtube.com/shorts/%s", video_id)
        return video_id
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(f"YouTube upload failed: {exc}") from exc
