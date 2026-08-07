"""
One-time helper: generates a YouTube OAuth refresh token.

Run this locally (NOT in GitHub Actions) once, following SETUP.md. It
opens a browser for you to sign in and grant upload permission, then
prints a refresh token you paste into your GitHub Secrets as
YOUTUBE_REFRESH_TOKEN.

Usage:
    python scripts/get_youtube_refresh_token.py --client-secrets client_secret.json
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a YouTube API refresh token.")
    parser.add_argument(
        "--client-secrets",
        default="client_secret.json",
        help="Path to the OAuth client secrets JSON downloaded from Google Cloud Console.",
    )
    args = parser.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "google-auth-oauthlib is not installed. Run:\n"
            "  pip install -r requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, scopes)
    credentials = flow.run_local_server(port=0)

    print("\nSuccess! Add these as GitHub Secrets:\n")
    print(f"YOUTUBE_CLIENT_ID={credentials.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={credentials.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")


if __name__ == "__main__":
    main()
