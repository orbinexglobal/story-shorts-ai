"""Upload the rendered Short to YouTube via the Data API v3."""

from __future__ import annotations

from pathlib import Path

from config.logging_setup import get_logger
from config.settings import Config
from providers.base import ProviderError
from youtube.auth import get_credentials

logger = get_logger(__name__)


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
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise ProviderError(
            "google-api-python-client is not installed. Run "
            "`pip install -r requirements.txt`."
        ) from exc

    credentials = get_credentials()
    youtube = build("youtube", "v3", credentials=credentials)

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
