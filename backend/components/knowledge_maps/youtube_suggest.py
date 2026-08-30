"""YouTube video suggestion using YouTube Data API v3 (Step 6).

Searches YouTube by topic and returns video cards the frontend renders in a grid.
Requires YOUTUBE_API_KEY in .env. If the key is missing, raises RuntimeError
so the route returns HTTP 501 with a clear hint.

Public API:
  suggest_videos(topic, max_results) -> list[YoutubeVideoCard]
"""
from __future__ import annotations

from backend.common.config import settings
from backend.components.knowledge_maps.schemas import YoutubeVideoCard

_YT_API_SERVICE = "youtube"
_YT_API_VERSION = "v3"


def suggest_videos(topic: str, max_results: int = 6) -> list[YoutubeVideoCard]:
    """Search YouTube Data API v3 for videos matching topic.

    Raises:
      RuntimeError  — YOUTUBE_API_KEY not set (→ HTTP 501)
      RuntimeError  — API quota exceeded or other Google API error (→ HTTP 429/502)
      ValueError    — empty topic (→ HTTP 400)
    """
    if not topic.strip():
        raise ValueError("Topic cannot be empty.")

    api_key = settings.youtube_api_key
    if not api_key or not api_key.strip():
        raise RuntimeError(
            "YOUTUBE_API_KEY is not set in .env. "
            "Get a free key at https://console.cloud.google.com/ "
            "(YouTube Data API v3, free tier = 10,000 units/day)."
        )

    try:
        from googleapiclient.discovery import build  # optional dep — lazy import
        from googleapiclient.errors import HttpError
    except ImportError as exc:
        raise RuntimeError(
            "google-api-python-client is not installed. "
            "Run: pip install google-api-python-client"
        ) from exc

    try:
        youtube = build(
            _YT_API_SERVICE,
            _YT_API_VERSION,
            developerKey=api_key.strip(),
            cache_discovery=False,  # avoids file-system cache warnings
        )
        response = (
            youtube.search()
            .list(
                q=topic.strip(),
                part="snippet",
                type="video",
                maxResults=max_results,
                relevanceLanguage="en",
                safeSearch="strict",   # student-facing app
                videoEmbeddable="true",
            )
            .execute()
        )
    except HttpError as exc:
        status = exc.resp.status if exc.resp else 0
        if status == 403:
            raise RuntimeError(
                "YouTube Data API quota exceeded or API key invalid. "
                "Free tier allows ~100 searches/day."
            ) from exc
        raise RuntimeError(f"YouTube API error {status}: {exc!s}") from exc

    cards: list[YoutubeVideoCard] = []
    for item in response.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})
        # Prefer medium thumbnail; fall back to default
        thumb = (
            thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
            or ""
        )
        cards.append(
            YoutubeVideoCard(
                title=snippet.get("title", "Untitled"),
                url=f"https://www.youtube.com/watch?v={video_id}",
                thumbnail=thumb,
                channel=snippet.get("channelTitle", ""),
            )
        )

    return cards
