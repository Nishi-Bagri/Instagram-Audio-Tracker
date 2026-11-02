import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import plotly.express as px
import streamlit as st

from audio_workflow import process_reel
from reel_collector import normalize_reel_url
from database.connection import SessionLocal
from database.models import Reel
from sqlalchemy.orm import joinedload


BASE_DIR = Path(__file__).resolve().parent


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Instagram Audio Tracker",
    page_icon="🎵",
    layout="wide",
)


# =========================================================
# STYLING
# =========================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.7rem;
        padding-bottom: 2rem;
    }

    [data-testid="stMetric"] {
        background: rgba(128, 128, 128, 0.08);
        border: 1px solid rgba(128, 128, 128, 0.22);
        padding: 16px;
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def is_valid_instagram_url(value: str) -> bool:
    """
    Accept:
    1. Instagram Reel URL
    2. Instagram Original Audio URL

    Reject unrelated Instagram URLs.
    """

    if not isinstance(value, str) or not value.strip():
        return False

    try:
        parsed = urlparse(value.strip())

        host = (parsed.hostname or "").lower()

        if parsed.scheme not in {"http", "https"}:
            return False

        if not (
            host == "instagram.com"
            or host.endswith(".instagram.com")
        ):
            return False

        path_parts = [
            part for part in parsed.path.split("/")
            if part
        ]

        # Reel URL:
        # instagram.com/reel/SHORTCODE/

        if (
            len(path_parts) >= 2
            and path_parts[0].lower() == "reel"
        ):
            return bool(path_parts[1])

        # Original Audio URL:
        # instagram.com/reels/audio/AUDIO_ID/

        if (
            len(path_parts) >= 3
            and path_parts[0].lower() == "reels"
            and path_parts[1].lower() == "audio"
        ):
            return path_parts[2].isdigit()

        return False

    except ValueError:
        return False


def get_input_type(value: str) -> str:
    """Identify whether input is a Reel or Original Audio URL."""

    parsed = urlparse(value.strip())

    path_parts = [
        part for part in parsed.path.split("/")
        if part
    ]

    if path_parts and path_parts[0].lower() == "reel":
        return "Instagram Reel"

    return "Instagram Original Audio"


def load_database_data():
    """
    Fetch Reel records and their associated Audio records
    directly from PostgreSQL.
    """

    db = SessionLocal()

    try:

        reels = (
            db.query(Reel)
            .options(joinedload(Reel.audio))
            .order_by(Reel.first_discovered_at.desc())
            .all()
        )

        records = []

        for reel in reels:

            metadata = {}

            if reel.metadata_json:

                try:
                    metadata = json.loads(reel.metadata_json)

                    if not isinstance(metadata, dict):
                        metadata = {}

                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            audio = reel.audio

            records.append(
                {
                    "reel_url": reel.reel_url,
                    "audio_id": (
                        audio.audio_id if audio else ""
                    ),
                    "creator_username": (
                        reel.creator_username or ""
                    ),
                    "posted_at": reel.posted_at,
                    "first_discovered_at": (
                        reel.first_discovered_at
                    ),
                    "metadata_available": metadata.get(
                        "available", False
                    ),
                    "metadata": metadata.get("text", ""),
                    "audio_title": (
                        audio.title if audio else ""
                    ),
                    "audio_artist": (
                        audio.artist if audio else ""
                    ),
                }
            )

        return pd.DataFrame(records)

    finally:
        db.close()


def clean_metadata_flag(series: pd.Series) -> pd.Series:
    """Convert metadata availability values into Boolean values."""

    return (
        series.astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    )


# =========================================================
# HEADER
# =========================================================

st.title("🎵 Instagram Audio Tracker")

st.caption(
    "Track Reels associated with an audio and analyse posting trends."
)


# =========================================================
# SIDEBAR: URL INPUT
# =========================================================

with st.sidebar:

    st.header("Track an Audio")

    reel_input = st.text_input(
        "Instagram Reel / Original Audio URL",
        placeholder="https://www.instagram.com/reel/...",
        help=(
            "Enter an Instagram Reel URL or "
            "an Original Audio URL."
        ),
    )

    analyze_clicked = st.button(
        "Analyze",
        type="primary",
        width="stretch",
    )

    st.divider()

    st.subheader("Data Source")

    st.code("PostgreSQL: instagram_audio_tracker")

    st.caption(
        "Dashboard data is fetched directly from PostgreSQL."
    )

    refresh_clicked = st.button(
        "Refresh Dashboard",
        width="stretch",
    )


# =========================================================
# ANALYZE URL WORKFLOW
# =========================================================

if analyze_clicked:

    if not reel_input.strip():

        st.sidebar.error(
            "Please enter an Instagram Reel or Original Audio URL."
        )

    elif not is_valid_instagram_url(reel_input):

        st.sidebar.error(
            "Invalid URL. Enter a valid Instagram Reel "
            "or Original Audio URL."
        )

    else:

        try:

            input_url = reel_input.strip()

            input_type = get_input_type(input_url)

            # Normalize Reel URLs only.
            # Preserve Original Audio URL structure.

            if input_type == "Instagram Reel":

                input_url = normalize_reel_url(input_url)

            with st.spinner(
                "Analyzing audio, collecting Reel links "
                "and updating PostgreSQL..."
            ):

                result = process_reel(input_url)

            audio_info = result.get("audio_info", {})

            collection_result = result.get(
                "collection_result", {}
            )

            sync_result = result.get(
                "sync_result", {}
            )

            st.success(
                "Audio processed successfully!"
            )

            st.write(
                f"**Input Type:** {input_type}"
            )

            st.write(
                f"**Audio ID:** "
                f"{audio_info.get('audio_id', 'Unknown')}"
            )

            st.write(
                f"**Audio Title:** "
                f"{audio_info.get('title') or 'Unknown Audio'}"
            )

            st.write(
                f"**Artist:** "
                f"{audio_info.get('artist') or 'Unknown Artist'}"
            )

            st.info(
                "New Reel links discovered: "
                f"{collection_result.get('new_links', 0)}"
            )

            st.success(
                "New database records: "
                f"{sync_result.get('new_reels', 0)}"
            )

            st.info(
                "Total Reels stored for this audio: "
                f"{sync_result.get('total_reels', 0)}"
            )

            st.rerun()

        except Exception as error:

            st.error(
                f"Workflow failed: {error}"
            )


# =========================================================
# REFRESH DASHBOARD
# =========================================================

if refresh_clicked:
    st.rerun()


# =========================================================
# LOAD DATA FROM POSTGRESQL
# =========================================================

try:

    df = load_database_data()

except Exception as error:

    st.error(
        f"Unable to load data from PostgreSQL: {error}"
    )

    st.stop()


# =========================================================
# EMPTY DATABASE HANDLING
# =========================================================

if df.empty:

    st.warning(
        "No Reel records found in PostgreSQL. "
        "Enter an Instagram Reel URL or Original Audio URL "
        "to start tracking."
    )

    st.stop()


# =========================================================
# DATA CLEANING
# =========================================================

df["reel_url"] = (
    df["reel_url"]
    .fillna("")
    .astype(str)
    .str.strip()
)

df = df[df["reel_url"] != ""].copy()

if df.empty:

    st.warning(
        "No valid Reel URLs are available in the database."
    )

    st.stop()


# Normalize URLs to avoid duplicate records.

df["normalized_url"] = df["reel_url"].map(
    normalize_reel_url
)

df = df.drop_duplicates(
    subset=["normalized_url"],
    keep="last",
).copy()


# Clean audio IDs.

df["audio_id"] = (
    df["audio_id"]
    .fillna("")
    .astype(str)
    .str.strip()
)


# Convert date columns.

for column in ["posted_at", "first_discovered_at"]:

    df[column] = pd.to_datetime(
        df[column],
        errors="coerce",
    )


# Clean creator usernames.

df["creator_username"] = (
    df["creator_username"]
    .fillna("")
    .astype(str)
)


# Clean audio information.

for column in ["audio_title", "audio_artist"]:

    df[column] = (
        df[column]
        .fillna("")
        .astype(str)
    )


# Metadata availability cleaning.

df["metadata_available"] = clean_metadata_flag(
    df["metadata_available"]
)


# Convert dates to date objects.

df["posted_at"] = df["posted_at"].dt.date

df["first_discovered_at"] = (
    df["first_discovered_at"].dt.date
)


# =========================================================
# AUDIO FILTER
# =========================================================

st.divider()

st.subheader("🎵 Audio-wise Analytics")

audio_options = (
    df[
        ["audio_id", "audio_title", "audio_artist"]
    ]
    .drop_duplicates(subset=["audio_id"])
)


audio_labels = {
    "all": "All Audios — Combined Analytics"
}


for _, row in audio_options.iterrows():

    audio_id = row["audio_id"]

    if not audio_id:
        continue

    title = row["audio_title"] or "Unknown Audio"

    artist = row["audio_artist"] or "Unknown Artist"

    audio_labels[audio_id] = (
        f"{title} - {artist} ({audio_id})"
    )


selected_audio = st.selectbox(
    "Select Original Audio",
    options=list(audio_labels.keys()),
    format_func=lambda value: audio_labels[value],
)


# Apply selected audio filter.

if selected_audio != "all":

    df = df[
        df["audio_id"] == selected_audio
    ].copy()


if df.empty:

    st.warning(
        "No Reel records found for the selected audio."
    )

    st.stop()


# =========================================================
# KPI CARDS
# =========================================================

today = pd.Timestamp.now().date()

today_count = int(
    (df["posted_at"] == today).sum()
)

metadata_count = int(
    df["metadata_available"].sum()
)

col1, col2, col3 = st.columns(3)


col1.metric(
    "Unique Reels Collected",
    f"{len(df):,}",
)

col2.metric(
    "Reels Posted Today",
    f"{today_count:,}",
)

col3.metric(
    "Records with Metadata",
    f"{metadata_count:,}",
)


st.info(
    "These counts represent unique Reel records stored in "
    "your PostgreSQL database. They do not represent "
    "Instagram's global total for the audio."
)


# =========================================================
# POSTING ANALYTICS
# =========================================================

st.divider()

st.subheader("📊 Posting Analytics")

valid_dates = df.dropna(
    subset=["posted_at"]
).copy()


if valid_dates.empty:

    st.warning(
        "No valid posting dates are available for the charts."
    )

else:

    daily = (
        valid_dates
        .groupby("posted_at")
        .size()
        .reset_index(name="Reels posted")
        .sort_values("posted_at")
    )

    daily["posted_at"] = pd.to_datetime(
        daily["posted_at"]
    )

    min_date = daily["posted_at"].min().date()

    max_date = daily["posted_at"].max().date()

    filter_col1, filter_col2 = st.columns([1, 2])


    with filter_col1:

        date_filter = st.selectbox(
            "Select Date Range",
            [
                "Last 7 Days",
                "Last 30 Days",
                "All Dates",
                "Custom Range",
            ],
            index=1,
        )


    start_date = min_date

    end_date = max_date


    if date_filter == "Last 7 Days":

        start_date = max(
            min_date,
            today - pd.Timedelta(days=6),
        )

        end_date = min(max_date, today)


    elif date_filter == "Last 30 Days":

        start_date = max(
            min_date,
            today - pd.Timedelta(days=29),
        )

        end_date = min(max_date, today)


    elif date_filter == "Custom Range":

        with filter_col2:

            selected_range = st.date_input(
                "Choose Date Range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
            )


        if (
            isinstance(selected_range, (tuple, list))
            and len(selected_range) == 2
        ):

            start_date, end_date = selected_range

        elif (
            isinstance(selected_range, (tuple, list))
            and len(selected_range) == 1
        ):

            start_date = end_date = selected_range[0]

        else:

            st.info(
                "Please select both a start date and an end date."
            )

            st.stop()


    # Apply selected date range.

    filtered_daily = daily[
        (daily["posted_at"].dt.date >= start_date)
        & (daily["posted_at"].dt.date <= end_date)
    ].copy()


    if filtered_daily.empty:

        st.info(
            "No collected Reels were posted in this date range."
        )

    else:

        filtered_daily["Date"] = (
            filtered_daily["posted_at"]
            .dt.strftime("%d %b")
        )


        # Cumulative count within selected date range.

        filtered_daily["Cumulative Reels"] = (
            filtered_daily["Reels posted"].cumsum()
        )


        chart_left, chart_right = st.columns(2)


        # -------------------------------------------------
        # DAILY BAR CHART
        # -------------------------------------------------

        with chart_left:

            daily_fig = px.bar(
                filtered_daily,
                x="Date",
                y="Reels posted",
                title="Daily Reel Creation",
                labels={
                    "Date": "Posting Date",
                    "Reels posted": "Collected Reels",
                },
                text="Reels posted",
            )

            daily_fig.update_traces(
                textposition="outside",
                cliponaxis=False,
            )

            daily_fig.update_layout(
                height=420,
                margin=dict(
                    l=15,
                    r=15,
                    t=65,
                    b=45,
                ),
                xaxis_title="Posting Date",
                yaxis_title="Number of Reels",
                xaxis=dict(
                    type="category",
                    tickangle=-45,
                ),
                showlegend=False,
            )

            st.plotly_chart(
                daily_fig,
                width="stretch",
            )


        # -------------------------------------------------
        # CUMULATIVE LINE CHART
        # -------------------------------------------------

        with chart_right:

            cumulative_fig = px.line(
                filtered_daily,
                x="Date",
                y="Cumulative Reels",
                title="Cumulative Collected Reels",
                markers=True,
                labels={
                    "Date": "Posting Date",
                    "Cumulative Reels": "Collected Reels",
                },
            )

            cumulative_fig.update_traces(
                line=dict(width=3),
                marker=dict(size=7),
            )

            cumulative_fig.update_layout(
                height=420,
                margin=dict(
                    l=15,
                    r=15,
                    t=65,
                    b=45,
                ),
                xaxis_title="Posting Date",
                yaxis_title="Cumulative Reels",
                xaxis=dict(
                    type="category",
                    tickangle=-45,
                ),
                showlegend=False,
            )

            st.plotly_chart(
                cumulative_fig,
                width="stretch",
            )


        st.caption(
            f"Showing {len(filtered_daily)} posting dates "
            f"from {start_date:%d %b %Y} "
            f"to {end_date:%d %b %Y}. "
            "Counts are based only on collected records."
        )


# =========================================================
# REEL EXPLORER
# =========================================================

st.divider()

st.subheader("🔎 Reel Explorer")

filter_col1, filter_col2 = st.columns([2, 1])


with filter_col1:

    search_text = st.text_input(
        "Search Creator or Reel URL",
        placeholder="Type a username or URL...",
    )


with filter_col2:

    date_options = sorted(
        [
            str(date_value)
            for date_value in df["posted_at"].dropna().unique()
        ],
        reverse=True,
    )

    selected_date = st.selectbox(
        "Posting Date",
        ["All Dates"] + date_options,
    )


filtered = df.copy()


# Search by username or Reel URL.

if search_text.strip():

    term = search_text.strip().lower()

    filtered = filtered[
        filtered["reel_url"].str.lower().str.contains(
            term,
            na=False,
            regex=False,
        )
        |
        filtered["creator_username"].str.lower().str.contains(
            term,
            na=False,
            regex=False,
        )
    ]


# Filter by posting date.

if selected_date != "All Dates":

    filtered = filtered[
        filtered["posted_at"].astype(str) == selected_date
    ]


# Select columns for display.

display_columns = [
    column
    for column in [
        "audio_id",
        "audio_title",
        "audio_artist",
        "creator_username",
        "posted_at",
        "first_discovered_at",
        "reel_url",
        "metadata_available",
    ]
    if column in filtered.columns
]


view = filtered[display_columns].copy()


# Rename columns for a cleaner dashboard.

view = view.rename(
    columns={
        "audio_id": "Audio ID",
        "audio_title": "Audio Title",
        "audio_artist": "Audio Artist",
        "creator_username": "Creator Username",
        "posted_at": "Posting Date",
        "first_discovered_at": "First Discovered",
        "reel_url": "Reel URL",
        "metadata_available": "Metadata Available",
    }
)


st.caption(
    f"Showing {len(view):,} of {len(df):,} "
    "unique collected Reels."
)


st.dataframe(
    view,
    width="stretch",
    hide_index=True,
    column_config={
        "Reel URL": st.column_config.LinkColumn(
            "Reel URL",
            display_text="Open Reel",
        )
    },
)


# =========================================================
# CSV DOWNLOAD
# =========================================================

st.download_button(
    "Download Filtered Records as CSV",
    data=view.to_csv(index=False).encode("utf-8"),
    file_name="instagram_reels_filtered.csv",
    mime="text/csv",
)


# =========================================================
# METRIC DEFINITIONS
# =========================================================

with st.expander("Metric Definitions and Limitations"):

    st.markdown(
        """
        - **Unique Reels Collected:** Unique Reel URLs stored in PostgreSQL.
        - **Reels Posted Today:** Collected records whose posting date is today.
        - **Daily Reel Creation:** Collected records grouped by posting date.
        - **Cumulative Reels:** Running total within the selected chart date range.
        - **New Reels Discovered:** New Reel links identified during collection.
        - **New Database Records:** New Reel records inserted into PostgreSQL.
        - **Scan History:** Successful and failed scan details are recorded in PostgreSQL.
        - **Instagram-reported total:** Not currently captured by this dashboard.
        - Instagram access restrictions may prevent collecting every Reel associated with an audio.
        """
    )