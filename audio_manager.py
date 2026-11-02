
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
AUDIOS_DIR = BASE_DIR / "data" / "audios"


def get_audio_folder(audio_id):
    """
    Return the folder path for a specific Instagram audio.
    """

    if audio_id is None or not str(audio_id).isdigit():
        raise ValueError("Invalid Instagram Audio ID.")

    folder_name = f"audio_{audio_id}"

    return AUDIOS_DIR / folder_name


def create_audio_dataset(audio_info):
    """
    Create an audio-specific dataset folder.

    Preserve existing files and records.
    Update metadata only when valid values are available.
    """

    # Validate input
    if not isinstance(audio_info, dict):
        raise TypeError("audio_info must be a dictionary.")

    audio_id = audio_info.get("audio_id")

    if audio_id is None or not str(audio_id).isdigit():
        raise ValueError("A valid audio_id is required.")

    audio_folder = get_audio_folder(audio_id)

    # Create audio-specific directory
    audio_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    links_file = audio_folder / "collected_reel_links.txt"
    csv_file = audio_folder / "instagram_reels.csv"
    metadata_file = audio_folder / "metadata.json"

    # Create files only when they do not already exist
    if not links_file.exists():
        links_file.write_text(
            "",
            encoding="utf-8",
        )

    if not csv_file.exists():
        csv_file.write_text(
            "reel_url,creator_username,posted_at,"
            "first_discovered_at,metadata_available,metadata\n",
            encoding="utf-8",
        )

    # Preserve and update existing metadata
    if metadata_file.exists():

        try:
            existing_metadata = json.loads(
                metadata_file.read_text(
                    encoding="utf-8-sig"
                )
            )

            if not isinstance(existing_metadata, dict):
                raise ValueError(
                    "Metadata JSON must contain an object."
                )

        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError(
                f"Existing metadata file is invalid: {metadata_file}"
            ) from error

        # Update only with non-empty values
        existing_metadata.update({
            key: value
            for key, value in audio_info.items()
            if value is not None and value != ""
        })

        metadata = existing_metadata

    else:
        metadata = audio_info

    # Save metadata
    metadata_file.write_text(
        json.dumps(
            metadata,
            indent=4,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return audio_folder


if __name__ == "__main__":

    test_audio = {
        "audio_id": "2500397173515471",
        "artist": "Akhil",
        "title": "Zindagi",
        "audio_url": (
            "https://www.instagram.com/reels/audio/"
            "2500397173515471/"
        ),
    }

    folder = create_audio_dataset(test_audio)

    print("\nAudio dataset ready!")
    print("Folder:", folder)

    print("\nFiles:")

    for file in folder.iterdir():
        print("-", file.name)

    print("\nMetadata:")

    metadata_file = folder / "metadata.json"

    metadata = json.loads(
        metadata_file.read_text(encoding="utf-8-sig")
    )

    print(
        json.dumps(
            metadata,
            indent=4,
            ensure_ascii=False,
        )
    )
