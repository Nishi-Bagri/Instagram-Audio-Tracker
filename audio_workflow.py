
import csv
import json
from datetime import datetime
from pathlib import Path

from audio_detector import detect_audio_from_url
from audio_manager import create_audio_dataset
from reel_collector import collect_reel_links
from extract_metadata import main as extract_metadata_main

from database.connection import SessionLocal
from database.crud import (
    get_audio_by_audio_id,
    create_audio,
    create_scan_history,
)
from database.models import Reel


# =========================================================
# DATE AND METADATA HELPERS
# =========================================================

def parse_date(value):
    """Convert an ISO date string into Python datetime."""

    if not value:
        return None

    if not isinstance(value, str):
        return None

    try:
        value = value.strip()

        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        return datetime.fromisoformat(value)

    except ValueError:
        return None


def is_metadata_available(value):
    """Convert CSV boolean-like values into a Python boolean."""

    return str(value or "").strip().lower() in (
        "true",
        "1",
        "yes",
    )


# =========================================================
# SCAN HISTORY
# =========================================================

def record_scan_history(
    audio_db_id,
    new_reels,
    total_reels,
    status,
):
    """Save scan execution details in PostgreSQL."""

    db = SessionLocal()

    try:
        create_scan_history(
            db,
            {
                "audio_id": audio_db_id,
                "new_reels_found": new_reels,
                "total_reels_found": total_reels,
                "status": status,
            },
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_audio_reel_count(audio_db_id):
    """Return the total Reel count for a particular audio."""

    db = SessionLocal()

    try:
        return (
            db.query(Reel)
            .filter(Reel.audio_id == audio_db_id)
            .count()
        )

    finally:
        db.close()


# =========================================================
# POSTGRESQL REEL SYNCHRONIZATION
# =========================================================

def sync_reels_to_database(audio_db_id, audio_folder):
    """
    Synchronize extracted Reel metadata with PostgreSQL.

    Existing Reel URLs are checked globally because reel_url
    has a UNIQUE constraint in the database.
    """

    if not audio_db_id:
        raise ValueError("Valid database audio ID is required.")

    csv_file = Path(audio_folder) / "instagram_reels.csv"

    if not csv_file.exists():
        raise FileNotFoundError(
            f"Metadata CSV not found: {csv_file}"
        )

    new_count = 0
    updated_count = 0
    skipped_count = 0

    db = SessionLocal()

    try:

        # STEP 1: Read CSV records.

        with csv_file.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            if not reader.fieldnames:
                raise ValueError(
                    "Metadata CSV is empty or missing its header."
                )

            if "reel_url" not in reader.fieldnames:
                raise ValueError(
                    "Required CSV column 'reel_url' is missing."
                )

            rows = list(reader)

        if not rows:
            print("No Reel records found in metadata CSV.")

        # STEP 2: Collect valid Reel URLs.

        reel_urls = {
            (row.get("reel_url") or "").strip()
            for row in rows
            if (row.get("reel_url") or "").strip()
        }

        # STEP 3: Fetch only matching existing records.

        if reel_urls:

            existing_reels = (
                db.query(Reel)
                .filter(Reel.reel_url.in_(reel_urls))
                .all()
            )

        else:
            existing_reels = []

        existing_map = {
            reel.reel_url: reel
            for reel in existing_reels
        }

        # STEP 4: Process each CSV record.

        for row in rows:

            reel_url = (
                row.get("reel_url") or ""
            ).strip()

            if not reel_url:
                continue

            creator = (
                row.get("creator_username") or ""
            ).strip()

            posted_at = parse_date(
                row.get("posted_at")
            )

            metadata_text = (
                row.get("metadata") or ""
            ).strip()

            metadata_available = is_metadata_available(
                row.get("metadata_available")
            )

            metadata_json = None

            if metadata_text or metadata_available:

                metadata_json = json.dumps(
                    {
                        "text": metadata_text,
                        "available": metadata_available,
                    },
                    ensure_ascii=False,
                )

            existing_reel = existing_map.get(reel_url)

            # STEP 5: Handle existing Reel.

            if existing_reel:

                # Preserve the existing audio association.

                if existing_reel.audio_id != audio_db_id:
                    skipped_count += 1
                    continue

                changed = False

                # Fill missing creator information.

                if (
                    not existing_reel.creator_username
                    and creator
                ):
                    existing_reel.creator_username = creator
                    changed = True

                # Fill missing posting date.

                if (
                    existing_reel.posted_at is None
                    and posted_at
                ):
                    existing_reel.posted_at = posted_at
                    changed = True

                # Never overwrite useful metadata with empty text.

                if (
                    metadata_text
                    and metadata_json
                    and existing_reel.metadata_json != metadata_json
                ):
                    existing_reel.metadata_json = metadata_json
                    changed = True

                if changed:
                    updated_count += 1

            # STEP 6: Insert new Reel.

            else:

                first_discovered_at = parse_date(
                    row.get("first_discovered_at")
                )

                new_reel = Reel(
                    reel_url=reel_url,
                    audio_id=audio_db_id,
                    creator_username=creator or None,
                    posted_at=posted_at,
                    metadata_json=metadata_json,
                )

                if first_discovered_at:
                    new_reel.first_discovered_at = (
                        first_discovered_at
                    )

                db.add(new_reel)

                # Avoid duplicate processing within the same CSV.

                existing_map[reel_url] = new_reel

                new_count += 1

        # STEP 7: Commit database changes.

        db.commit()

        # STEP 8: Get total records for this audio.

        total_count = (
            db.query(Reel)
            .filter(Reel.audio_id == audio_db_id)
            .count()
        )

        print("\n=== POSTGRESQL REEL SYNC SUMMARY ===")
        print("New Reels saved:", new_count)
        print("Existing Reels updated:", updated_count)
        print("Reels skipped (other audio):", skipped_count)
        print("Total Reels for this audio:", total_count)

        return {
            "new_reels": new_count,
            "updated_reels": updated_count,
            "skipped_reels": skipped_count,
            "total_reels": total_count,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# =========================================================
# COMPLETE AUDIO TRACKING WORKFLOW
# =========================================================

def process_reel(instagram_url):
    """
    Execute the complete Instagram Audio Tracker workflow.

    Supports:
    1. Instagram Reel URL
    2. Instagram Original Audio URL
    """

    if not instagram_url or not instagram_url.strip():
        raise ValueError(
            "Instagram Reel or Original Audio URL is required."
        )

    audio_db_id = None
    sync_result = None

    try:

        # STEP 1: Detect audio.

        print("\n=== STEP 1: DETECT AUDIO ===")

        audio_info = detect_audio_from_url(instagram_url.strip())

        if not isinstance(audio_info, dict):
            raise ValueError(
                "Audio detection returned invalid data."
            )

        audio_id = audio_info.get("audio_id")
        audio_url = audio_info.get("audio_url")

        if (
            audio_id is None
            or not str(audio_id).isdigit()
            or not audio_url
        ):
            raise ValueError(
                "Audio detection did not return valid audio details."
            )

        audio_id = str(audio_id)

        print("Audio ID:", audio_id)
        print("Artist:", audio_info.get("artist"))
        print("Title:", audio_info.get("title"))
        print("Audio URL:", audio_url)

        # STEP 2: Prepare dataset.

        print("\n=== STEP 2: PREPARE DATASET ===")

        audio_folder = create_audio_dataset(audio_info)

        print("Dataset folder:", audio_folder)

        # STEP 3: Save or retrieve audio in PostgreSQL.

        print("\n=== STEP 3: SAVE AUDIO IN POSTGRESQL ===")

        db = SessionLocal()

        try:

            existing_audio = get_audio_by_audio_id(
                db,
                audio_id,
            )

            if existing_audio:

                audio = existing_audio

                print("Audio already exists in database.")

                # Update only missing audio details.

                audio_changed = False

                if not audio.title and audio_info.get("title"):
                    audio.title = audio_info["title"]
                    audio_changed = True

                if not audio.artist and audio_info.get("artist"):
                    audio.artist = audio_info["artist"]
                    audio_changed = True

                if not audio.audio_url and audio_url:
                    audio.audio_url = audio_url
                    audio_changed = True

                if audio_changed:
                    db.commit()

            else:

                audio = create_audio(
                    db,
                    {
                        "audio_id": audio_id,
                        "title": audio_info.get("title"),
                        "artist": audio_info.get("artist"),
                        "audio_url": audio_url,
                    },
                )

                print("New audio saved in PostgreSQL.")

            audio_db_id = audio.id

            print("Database Audio ID:", audio_db_id)

        finally:
            db.close()

        # STEP 4: Collect Reel links.

        print("\n=== STEP 4: COLLECT REEL LINKS ===")

        collection_result = collect_reel_links(
            audio_url=audio_url,
            audio_folder=audio_folder,
            max_scrolls=300,
            no_new_limit=10,
        )

        print(
            "Previously collected:",
            collection_result["previous_links"],
        )

        print(
            "New Reels found:",
            collection_result["new_links"],
        )

        print(
            "Total Reel links:",
            collection_result["total_links"],
        )

        # STEP 5: Extract metadata.

        print("\n=== STEP 5: EXTRACT REEL METADATA ===")

        extract_metadata_main(audio_folder)

        print("Metadata extraction completed.")

        # STEP 6: Synchronize with PostgreSQL.

        print("\n=== STEP 6: SYNC REELS TO POSTGRESQL ===")

        sync_result = sync_reels_to_database(
            audio_db_id=audio_db_id,
            audio_folder=audio_folder,
        )

        # STEP 7: Save successful scan history.

        print("\n=== STEP 7: SAVE SCAN HISTORY ===")

        record_scan_history(
            audio_db_id=audio_db_id,
            new_reels=sync_result["new_reels"],
            total_reels=sync_result["total_reels"],
            status="success",
        )

        print("Scan history saved successfully.")

        print("\n=== WORKFLOW COMPLETED ===")

        return {
            "audio_info": audio_info,
            "audio_folder": audio_folder,
            "collection_result": collection_result,
            "sync_result": sync_result,
        }

    except Exception:

        # Record failure if audio was saved successfully.

        if audio_db_id is not None:

            try:

                total_reels = get_audio_reel_count(
                    audio_db_id
                )

                record_scan_history(
                    audio_db_id=audio_db_id,
                    new_reels=(
                        sync_result["new_reels"]
                        if sync_result else 0
                    ),
                    total_reels=total_reels,
                    status="failed",
                )

                print("Failed scan recorded in database.")

            except Exception as history_error:

                print(
                    "Could not save failure history:",
                    history_error,
                )

        raise


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    instagram_url = input(
        "Enter Instagram Reel or Original Audio URL: "
    ).strip()

    try:

        result = process_reel(instagram_url)

        print("\n=== FINAL RESULT ===")

        print(
            "Audio:",
            result["audio_info"].get("title") or "Unknown Audio",
        )

        print(
            "Audio ID:",
            result["audio_info"]["audio_id"],
        )

        print("Folder:", result["audio_folder"])

        print(
            "New Reel links:",
            result["collection_result"]["new_links"],
        )

        print(
            "New database records:",
            result["sync_result"]["new_reels"],
        )

        print(
            "Updated database records:",
            result["sync_result"]["updated_reels"],
        )

        print(
            "Total Reels:",
            result["sync_result"]["total_reels"],
        )

    except Exception as error:

        print("\nApplication execution failed:", error)
