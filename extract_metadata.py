
import csv
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_DIR = Path(__file__).resolve().parent
BROWSER_PROFILE_DIR = BASE_DIR / "browser_profile"

COLUMNS = [
    "reel_url",
    "creator_username",
    "posted_at",
    "first_discovered_at",
    "metadata_available",
    "metadata",
]


def extract_creator(description):
    """Extract creator username from Instagram metadata."""

    patterns = [
        r"@\s*([A-Za-z0-9._]+)\s+on\s+",
        r"-\s*@?\s*([A-Za-z0-9._]+)\s+on\s+",
        r"^\s*@?\s*([A-Za-z0-9._]+)\s+on\s+",
    ]

    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)

        if match:
            return match.group(1)

    return ""


def extract_posted_date(description):
    """Extract posting date from Instagram metadata."""

    patterns = [
        r"\bon\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"\b([A-Za-z]+\s+\d{1,2},\s+\d{4})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)

        if match:
            try:
                return datetime.strptime(
                    match.group(1),
                    "%B %d, %Y",
                ).date().isoformat()

            except ValueError:
                continue

    return ""


def load_existing_records(output_file):
    """Load existing CSV records without losing their data."""

    records = {}

    if not output_file.exists():
        return records

    with output_file.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            url = (row.get("reel_url") or "").strip()

            if url:
                normalized = {
                    column: (row.get(column) or "")
                    for column in COLUMNS
                }

                records[url] = normalized

    return records


def load_reel_urls(input_file):
    """Load unique Reel URLs from the audio-specific text file."""

    if not input_file.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_file}"
        )

    with input_file.open(
        "r",
        encoding="utf-8-sig",
    ) as file:

        return list(dict.fromkeys(
            line.strip()
            for line in file
            if line.strip()
        ))


def needs_retry(record):
    """Check whether a record needs metadata extraction or retry."""

    return (
        not record.get("creator_username", "").strip()
        or not record.get("posted_at", "").strip()
        or str(
            record.get("metadata_available", "")
        ).lower() not in ("true", "1", "yes")
        or not record.get("metadata", "").strip()
    )


def extract_metadata(page, reel_url):
    """Extract metadata from an individual Instagram Reel."""

    page.goto(
        reel_url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(2500)

    description = page.locator(
        'meta[property="og:description"]'
    ).get_attribute("content") or ""

    creator = extract_creator(description)
    posted_at = extract_posted_date(description)

    return {
        "creator_username": creator,
        "posted_at": posted_at,
        "metadata_available": bool(description),
        "metadata": description,
    }


def save_records(records, output_file):
    """Safely save records using a temporary CSV file."""

    temp_file = output_file.with_name(
        f"{output_file.stem}.tmp{output_file.suffix}"
    )

    try:
        with temp_file.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=COLUMNS,
                extrasaction="ignore",
            )

            writer.writeheader()

            for record in records.values():
                writer.writerow({
                    column: record.get(column, "")
                    for column in COLUMNS
                })

        temp_file.replace(output_file)

    finally:
        if temp_file.exists():
            temp_file.unlink()


def main(audio_folder):
    """
    Extract metadata for Reel URLs belonging to one audio.

    All input and output files are taken from audio_folder.
    """

    audio_folder = Path(audio_folder)

    input_file = audio_folder / "collected_reel_links.txt"
    output_file = audio_folder / "instagram_reels.csv"

    if not audio_folder.exists():
        raise FileNotFoundError(
            f"Audio folder not found: {audio_folder}"
        )

    # STEP 1: Load Reel URLs and existing CSV records.
    reel_urls = load_reel_urls(input_file)

    records = load_existing_records(output_file)

    # STEP 2: Add newly discovered URLs.
    for url in reel_urls:

        if url not in records:

            records[url] = {
                "reel_url": url,
                "creator_username": "",
                "posted_at": "",
                "first_discovered_at": (
                    datetime.now().date().isoformat()
                ),
                "metadata_available": False,
                "metadata": "",
            }

    # STEP 3: Identify records requiring extraction or retry.
    retry_urls = [
        url
        for url, record in records.items()
        if needs_retry(record)
    ]

    print("\n========== METADATA EXTRACTION ==========")
    print("Audio folder:", audio_folder)
    print("Total Reel URLs:", len(reel_urls))
    print("Total unique CSV records:", len(records))
    print("Records requiring metadata:", len(retry_urls))

    if not retry_urls:

        print("\nAll records already have metadata fields populated.")
        print("CSV:", output_file)

        return

    # STEP 4: Open Instagram and extract metadata.
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

            for number, url in enumerate(
                retry_urls,
                start=1,
            ):

                print(
                    f"\n[{number}/{len(retry_urls)}] {url}"
                )

                try:

                    extracted = extract_metadata(
                        page,
                        url,
                    )

                    existing = records[url]

                    # Update only fields where extraction found a value.
                    for field in (
                        "creator_username",
                        "posted_at",
                        "metadata",
                    ):

                        if extracted[field]:
                            existing[field] = extracted[field]

                    if extracted["metadata_available"]:
                        existing["metadata_available"] = True

                    if not existing["creator_username"]:
                        print("  Username still unavailable.")

                    if not existing["posted_at"]:
                        print("  Posted date still unavailable.")

                    print(
                        "  Metadata available:",
                        existing["metadata_available"],
                    )

                except Exception as error:

                    print("  Extraction failed:", error)

                # Save after every Reel.
                save_records(records, output_file)

                page.wait_for_timeout(2000)

        finally:

            context.close()

    # STEP 5: Final summary.
    missing_usernames = sum(
        not record.get("creator_username", "").strip()
        for record in records.values()
    )

    missing_dates = sum(
        not record.get("posted_at", "").strip()
        for record in records.values()
    )

    print("\n========== TRACKER SUMMARY ==========")
    print("Total unique Reel records:", len(records))
    print("Missing creator usernames:", missing_usernames)
    print("Missing posted dates:", missing_dates)
    print("CSV saved at:", output_file)


if __name__ == "__main__":

    test_audio_folder = (
        BASE_DIR
        / "data"
        / "audios"
        / "audio_2500397173515471"
    )

    main(test_audio_folder)
