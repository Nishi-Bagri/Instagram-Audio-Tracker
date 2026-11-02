import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from reel_collector import normalize_reel_url


BASE_DIR = Path(__file__).resolve().parent
BROWSER_PROFILE_DIR = BASE_DIR / "browser_profile"


# =========================================================
# URL VALIDATION
# =========================================================

def validate_instagram_url(url):
    """
    Validate Instagram Reel and Original Audio URLs.

    Supported:
    1. https://www.instagram.com/reel/SHORTCODE/
    2. https://www.instagram.com/reels/audio/AUDIO_ID/
    """

    if not isinstance(url, str) or not url.strip():
        raise ValueError("Please provide an Instagram URL.")

    parsed = urlparse(url.strip())

    hostname = (parsed.hostname or "").lower()

    if (
        parsed.scheme not in ("http", "https")
        or hostname not in ("instagram.com", "www.instagram.com")
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Please provide a valid Instagram URL.")

    path = parsed.path.rstrip("/")

    if re.fullmatch(r"/reel/[^/]+", path, re.IGNORECASE):
        return "reel"

    if re.fullmatch(
        r"/reels/audio/\d+",
        path,
        re.IGNORECASE,
    ):
        return "audio"

    raise ValueError(
        "Unsupported Instagram URL. Please provide either "
        "a Reel URL or an Original Audio URL."
    )


# =========================================================
# JSON EXTRACTION
# =========================================================

def extract_json_object(html, key):
    """
    Extract a JSON object associated with a given key.

    Handles nested JSON objects, quoted strings and escaped
    characters.
    """

    match = re.search(
        rf'"{re.escape(key)}"\s*:',
        html,
    )

    if not match:
        return None

    start = html.find("{", match.end())

    if start == -1:
        return None

    depth = 0
    inside_string = False
    escaped = False

    for index in range(start, len(html)):

        char = html[index]

        if inside_string:

            if escaped:
                escaped = False

            elif char == "\\":
                escaped = True

            elif char == '"':
                inside_string = False

        else:

            if char == '"':
                inside_string = True

            elif char == "{":
                depth += 1

            elif char == "}":
                depth -= 1

                if depth == 0:

                    try:
                        return json.loads(
                            html[start:index + 1]
                        )

                    except json.JSONDecodeError:
                        return None

    return None


# =========================================================
# BROWSER PAGE FETCHING
# =========================================================

def fetch_instagram_page(url):
    """
    Open an Instagram page using the persistent browser profile
    and return its HTML content.

    Browser context is always closed.
    """

    BROWSER_PROFILE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sync_playwright() as p:

        context = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
        )

        try:

            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )

            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            if response and response.status >= 400:

                raise RuntimeError(
                    f"Instagram returned HTTP {response.status}"
                )

            page.wait_for_timeout(5000)

            return page.content()

        finally:
            context.close()


# =========================================================
# AUDIO METADATA EXTRACTION
# =========================================================

def extract_audio_metadata(html, expected_audio_id=None):
    """
    Extract audio ID, artist and title from music_asset_info.

    Returns None if music metadata is not available.
    """

    music_info = extract_json_object(
        html,
        "music_asset_info",
    )

    if not isinstance(music_info, dict):
        return None

    audio_id = music_info.get("audio_cluster_id")

    if (
        audio_id is None
        or not str(audio_id).isdigit()
    ):
        return None

    audio_id = str(audio_id)

    if (
        expected_audio_id is not None
        and audio_id != str(expected_audio_id)
    ):
        return None

    return {
        "audio_id": audio_id,
        "artist": music_info.get("display_artist"),
        "title": music_info.get("title"),
        "audio_url": (
            f"https://www.instagram.com/reels/audio/{audio_id}/"
        ),
    }

# =========================================================
# OPEN GRAPH METADATA EXTRACTION
# =========================================================

def extract_open_graph_metadata(html_content, audio_id):
    """
    Extract artist and title from Instagram Open Graph metadata.
    """

    match = re.search(
        r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']',
        html_content,
        re.IGNORECASE,
    )

    if not match:
        return None

    og_title = html.unescape(match.group(1))

    suffix = " on Instagram"

    if og_title.endswith(suffix):
        og_title = og_title[:-len(suffix)]

    if " | " not in og_title:
        return None

    artist, title = og_title.split(" | ", 1)

    artist = artist.strip()
    title = title.strip()

    if not artist or not title:
        return None

    return {
        "audio_id": str(audio_id),
        "artist": artist,
        "title": title,
        "audio_url": (
            f"https://www.instagram.com/reels/audio/{audio_id}/"
        ),
    }


# =========================================================
# AUDIO INFORMATION FROM AUDIO URL
# =========================================================

def detect_audio_from_audio_url(audio_url):
    """
    Extract audio ID, artist and title from an Instagram
    Original Audio page.
    """

    url_type = validate_instagram_url(audio_url)

    if url_type != "audio":
        raise ValueError(
            "This function accepts only Original Audio URLs."
        )

    parsed = urlparse(audio_url)

    match = re.fullmatch(
        r"/reels/audio/(\d+)/?",
        parsed.path,
        re.IGNORECASE,
    )

    if not match:
        raise ValueError(
            "Unable to extract a valid audio ID."
        )

    audio_id = match.group(1)

    result = {
        "audio_id": audio_id,
        "artist": None,
        "title": None,
        "audio_url": (
            f"https://www.instagram.com/reels/audio/{audio_id}/"
        ),
    }

    print("Opening Original Audio page...")

    page_html = fetch_instagram_page(result["audio_url"])

    # First attempt: music_asset_info JSON.
    metadata = extract_audio_metadata(
        page_html,
        expected_audio_id=audio_id,
    )

    # Second attempt: Open Graph metadata.
    if not metadata:

        metadata = extract_open_graph_metadata(
            page_html,
            audio_id,
        )

    if metadata:

        result.update(metadata)

        print("Audio metadata extracted successfully.")

    else:

        print(
            "Artist/title metadata was not found."
        )

    return result


# =========================================================
# AUDIO INFORMATION FROM REEL URL
# =========================================================

def detect_audio_from_reel(reel_url):
    """
    Detect original audio information from an Instagram Reel URL.
    """

    url_type = validate_instagram_url(reel_url)

    if url_type != "reel":
        raise ValueError(
            "detect_audio_from_reel() accepts only Reel URLs."
        )

    reel_url = normalize_reel_url(reel_url)

    html = fetch_instagram_page(reel_url)

    metadata = extract_audio_metadata(html)

    if not metadata:

        raise ValueError(
            "Music information not found in Reel metadata."
        )

    return metadata


# =========================================================
# METADATA ENRICHMENT FROM ASSOCIATED REEL
# =========================================================

def enrich_audio_metadata_from_reel(audio_info, reel_url):
    """
    Attempt to recover missing artist/title information
    from a Reel associated with the same audio.

    Existing non-empty metadata is preserved.

    The Reel must expose matching audio metadata.
    """

    if not isinstance(audio_info, dict):
        raise TypeError("audio_info must be a dictionary.")

    audio_id = audio_info.get("audio_id")

    if (
        audio_id is None
        or not str(audio_id).isdigit()
    ):
        raise ValueError("A valid audio_id is required.")

    url_type = validate_instagram_url(reel_url)

    if url_type != "reel":
        raise ValueError(
            "Metadata enrichment requires an Instagram Reel URL."
        )

    reel_url = normalize_reel_url(reel_url)

    html = fetch_instagram_page(reel_url)

    metadata = extract_audio_metadata(
        html,
        expected_audio_id=str(audio_id),
    )

    if not metadata:

        print(
            "Matching audio metadata was not found in this Reel."
        )

        return audio_info

    if not audio_info.get("artist") and metadata.get("artist"):
        audio_info["artist"] = metadata["artist"]

    if not audio_info.get("title") and metadata.get("title"):
        audio_info["title"] = metadata["title"]

    if not audio_info.get("audio_url"):
        audio_info["audio_url"] = metadata["audio_url"]

    print("Audio metadata enrichment completed.")

    return audio_info


# =========================================================
# COMMON INPUT HANDLER
# =========================================================

def detect_audio_from_url(instagram_url):
    """
    Accept either a Reel URL or an Original Audio URL.

    Automatically selects the appropriate detection method.
    """

    url_type = validate_instagram_url(instagram_url)

    if url_type == "reel":

        print("Input type: Instagram Reel")

        return detect_audio_from_reel(instagram_url)

    if url_type == "audio":

        print("Input type: Instagram Original Audio")

        return detect_audio_from_audio_url(instagram_url)

    raise ValueError("Unsupported Instagram URL type.")



# =========================================================
# DEBUG ORIGINAL AUDIO PAGE
# =========================================================

def debug_audio_page(audio_url):
    html = fetch_instagram_page(audio_url)

    print("HTML Length:", len(html))

    for keyword in [
        "music_asset_info",
        "Amrinder Gill",
        "Raj Ranjodh",
        "Dr Zeus",
        "That Girl",
        "audio_cluster_id",
    ]:
        print(
            keyword,
            "FOUND" if keyword.lower() in html.lower()
            else "NOT FOUND"
        )

    debug_file = BASE_DIR / "audio_page_debug.html"

    debug_file.write_text(
        html,
        encoding="utf-8",
    )

    print("HTML saved to:", debug_file)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    instagram_url = input(
        "Enter Instagram Reel or Original Audio URL: "
    ).strip()

    try:

        result = detect_audio_from_url(instagram_url)

        print("\n=== DETECTED AUDIO ===")

        print("Audio ID:", result["audio_id"])
        print("Artist:", result["artist"])
        print("Title:", result["title"])
        print("Audio URL:", result["audio_url"])

    except Exception as error:

        print("\nAudio detection failed:", error)
