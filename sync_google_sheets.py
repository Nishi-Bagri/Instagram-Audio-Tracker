
import argparse
import csv
import os
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from reel_collector import normalize_reel_url


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

AUDIOS_DIR = BASE_DIR / "data" / "audios"

load_dotenv(BASE_DIR / ".env")

SERVICE_ACCOUNT_PATH = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE"
)

SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID")

WORKSHEET_NAME = os.getenv(
    "GOOGLE_WORKSHEET_NAME",
    "",
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


# =========================================================
# CONFIGURATION VALIDATION
# =========================================================

def validate_configuration():
    """Validate Google Sheets configuration."""

    if not SERVICE_ACCOUNT_PATH:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_FILE is missing in .env"
        )

    if not SPREADSHEET_ID:
        raise ValueError(
            "GOOGLE_SPREADSHEET_ID is missing in .env"
        )

    credentials_path = Path(SERVICE_ACCOUNT_PATH)

    if not credentials_path.is_absolute():
        credentials_path = BASE_DIR / credentials_path

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Google credentials file not found: {credentials_path}"
        )

    return credentials_path


# =========================================================
# AUDIO DATASET SELECTION
# =========================================================

def get_audio_csv(audio_id=None):
    """
    Locate the CSV file for the requested audio.

    If audio_id is not provided:
    - Automatically select the dataset if only one exists.
    - Ask the user to select one if multiple datasets exist.
    """

    if not AUDIOS_DIR.exists():
        raise FileNotFoundError(
            f"Audio datasets directory not found: {AUDIOS_DIR}"
        )

    audio_folders = sorted(
        folder
        for folder in AUDIOS_DIR.iterdir()
        if folder.is_dir() and folder.name.startswith("audio_")
    )

    if not audio_folders:
        raise FileNotFoundError(
            "No audio datasets found in data/audios."
        )

    if audio_id:

        if not str(audio_id).isdigit():
            raise ValueError("Invalid Instagram Audio ID.")

        selected_folder = AUDIOS_DIR / f"audio_{audio_id}"

        if not selected_folder.is_dir():
            raise FileNotFoundError(
                f"Dataset not found for Audio ID: {audio_id}"
            )

    elif len(audio_folders) == 1:

        selected_folder = audio_folders[0]

    else:

        print("\nAvailable Audio Datasets:")

        for index, folder in enumerate(audio_folders, start=1):
            print(f"{index}. {folder.name}")

        choice = input(
            "\nSelect dataset number: "
        ).strip()

        if not choice.isdigit():
            raise ValueError("Please enter a valid dataset number.")

        selected_index = int(choice)

        if selected_index < 1 or selected_index > len(audio_folders):
            raise ValueError("Invalid dataset selection.")

        selected_folder = audio_folders[selected_index - 1]

    csv_file = selected_folder / "instagram_reels.csv"

    if not csv_file.exists():
        raise FileNotFoundError(
            f"CSV file not found: {csv_file}"
        )

    return csv_file


# =========================================================
# READ AND VALIDATE CSV
# =========================================================

def read_csv_records(csv_file):
    """Read CSV records and validate required columns."""

    with csv_file.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        headers = reader.fieldnames

        if not headers:
            raise ValueError(
                "CSV file has no column headers."
            )

        if len(headers) != len(set(headers)):
            raise ValueError(
                "CSV contains duplicate column headers."
            )

        if "reel_url" not in headers:
            raise ValueError(
                "CSV must contain a reel_url column."
            )

        records = list(reader)

    return headers, records


# =========================================================
# NORMALIZE AND PREPARE RECORDS
# =========================================================

def prepare_records(headers, records):
    """
    Normalize Reel URLs and remove duplicate CSV records.
    """

    prepared_records = []
    seen_urls = set()

    for record in records:

        url = (record.get("reel_url") or "").strip()

        if not url:
            continue

        normalized_url = normalize_reel_url(url)

        if not normalized_url:
            continue

        if normalized_url in seen_urls:
            continue

        seen_urls.add(normalized_url)

        values = [
            (record.get(header) or "").strip()
            for header in headers
        ]

        # Store the normalized URL consistently.
        reel_url_index = headers.index("reel_url")
        values[reel_url_index] = normalized_url

        prepared_records.append(
            {
                "url": normalized_url,
                "values": values,
            }
        )

    return prepared_records


# =========================================================
# GOOGLE SHEETS CONNECTION
# =========================================================

def connect_to_google_sheets(credentials_path):
    """Authenticate and connect to Google Sheets."""

    credentials = Credentials.from_service_account_file(
        str(credentials_path),
        scopes=SCOPES,
    )

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    if WORKSHEET_NAME:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    else:
        worksheet = spreadsheet.sheet1

    return worksheet


# =========================================================
# COLUMN RANGE HELPER
# =========================================================

def get_last_column(headers):
    """Return the last spreadsheet column in A1 notation."""

    return gspread.utils.rowcol_to_a1(
        1,
        len(headers),
    ).rstrip("1")


# =========================================================
# GOOGLE SHEETS HEADER VALIDATION
# =========================================================

def validate_sheet_headers(worksheet, headers):
    """
    Validate existing Google Sheet headers.

    Create headers if the worksheet is empty.
    """

    existing_data = worksheet.get_all_values()

    if not existing_data:

        worksheet.update(
            range_name="A1",
            values=[headers],
            value_input_option="RAW",
        )

        existing_data = [headers]

    elif existing_data[0] != headers:

        raise ValueError(
            "Google Sheet headers do not match CSV headers. "
            "No Reel data was changed."
        )

    return existing_data


# =========================================================
# BUILD EXISTING REEL LOOKUP
# =========================================================

def build_existing_reel_map(existing_data, headers):
    """
    Map normalized Reel URLs to their Google Sheet row numbers
    and existing values.
    """

    reel_url_index = headers.index("reel_url")

    existing_reels = {}

    for row_number, row in enumerate(
        existing_data[1:],
        start=2,
    ):

        if reel_url_index >= len(row):
            continue

        url = (row[reel_url_index] or "").strip()

        if not url:
            continue

        normalized_url = normalize_reel_url(url)

        if not normalized_url:
            continue

        existing_values = [
            row[index] if index < len(row) else ""
            for index in range(len(headers))
        ]

        existing_reels[normalized_url] = {
            "row_number": row_number,
            "values": existing_values,
        }

    return existing_reels


# =========================================================
# GOOGLE SHEETS SYNCHRONIZATION
# =========================================================

def sync_to_google_sheets(audio_id=None):
    """
    Synchronize audio Reel CSV records with Google Sheets.

    Existing records are updated only when values change.
    New records are appended.
    Duplicate Reel URLs are ignored.
    """

    print("\n========== GOOGLE SHEETS SYNC ==========")

    # Step 1: Validate configuration.

    credentials_path = validate_configuration()

    # Step 2: Locate the selected audio CSV.

    csv_file = get_audio_csv(audio_id)

    print(f"CSV file: {csv_file}")

    # Step 3: Read CSV records.

    headers, records = read_csv_records(csv_file)

    prepared_records = prepare_records(
        headers,
        records,
    )

    print(f"CSV records found: {len(records)}")
    print(f"Valid unique Reel records: {len(prepared_records)}")

    # Step 4: Connect to Google Sheets.

    worksheet = connect_to_google_sheets(
        credentials_path
    )

    print(f"Google worksheet: {worksheet.title}")

    # Step 5: Validate headers.

    existing_data = validate_sheet_headers(
        worksheet,
        headers,
    )

    # Step 6: Build existing Reel lookup.

    existing_reels = build_existing_reel_map(
        existing_data,
        headers,
    )

    # Step 7: Compare records.

    updated_rows = []
    new_rows = []

    skipped_records = 0

    for record in prepared_records:

        url = record["url"]
        values = record["values"]

        existing_record = existing_reels.get(url)

        if existing_record:

            current_values = existing_record["values"]

            if current_values != values:

                updated_rows.append(
                    {
                        "row_number": existing_record["row_number"],
                        "values": values,
                    }
                )

            else:

                skipped_records += 1

        else:

            new_rows.append(values)

    # Step 8: Batch update existing rows.

    if updated_rows:

        batch_updates = []

        last_column = get_last_column(headers)

        for item in updated_rows:

            row_number = item["row_number"]

            batch_updates.append(
                {
                    "range": f"A{row_number}:{last_column}{row_number}",
                    "values": [item["values"]],
                }
            )

        worksheet.batch_update(
            data=batch_updates,
            value_input_option="RAW",
        )

    # Step 9: Append new records in one operation.

    if new_rows:

        worksheet.append_rows(
            new_rows,
            value_input_option="RAW",
        )

    # Step 10: Display summary.

    print("\n========== SYNC SUMMARY ==========")

    print(f"CSV records found: {len(records)}")

    print(
        f"Valid unique records: {len(prepared_records)}"
    )

    print(
        f"Existing rows updated: {len(updated_rows)}"
    )

    print(
        f"New rows added: {len(new_rows)}"
    )

    print(
        f"Unchanged records skipped: {skipped_records}"
    )

    print(
        "Google Sheets synchronization completed successfully."
    )

    return {
        "csv_records": len(records),
        "valid_unique_records": len(prepared_records),
        "updated_rows": len(updated_rows),
        "new_rows": len(new_rows),
        "skipped_records": skipped_records,
    }


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Synchronize Instagram Reel data with Google Sheets."
    )

    parser.add_argument(
        "--audio-id",
        type=str,
        help="Instagram Audio ID whose dataset should be synchronized.",
    )

    args = parser.parse_args()

    try:

        sync_to_google_sheets(
            audio_id=args.audio_id
        )

    except Exception as error:

        print(f"\nGoogle Sheets sync failed: {error}")

        raise
