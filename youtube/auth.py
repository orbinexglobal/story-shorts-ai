"""
YouTube Data API OAuth credential loading.

Builds a `google.oauth2.credentials.Credentials` object from a
long-lived refresh token stored in environment variables / GitHub
Secrets, rather than requiring an interactive browser login on every
run. See scripts/get_youtube_refresh_token.py (and SETUP.md) for how
to generate that refresh token once, locally.
"""

from __future__ import annotations

import os

from providers.base import ProviderError

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"


def get_credentials():
    """Build OAuth credentials from environment variables.

    Required env vars: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN.
    """
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise ProviderError(
            "google-auth is not installed. Run `pip install -r requirements.txt`."
        ) from exc

    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    missing = [
        name for name, val in [
            ("YOUTUBE_CLIENT_ID", client_id),
            ("YOUTUBE_CLIENT_SECRET", client_secret),
            ("YOUTUBE_REFRESH_TOKEN", refresh_token),
        ] if not val
    ]
    if missing:
        raise ProviderError(
            f"Missing required YouTube credentials: {', '.join(missing)}. "
            "See SETUP.md for how to generate them."
        )

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=_SCOPES,
    )
