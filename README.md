# Instagram Audio Tracker

## Project Overview

Instagram Audio Tracker is a Python-based application designed to track Instagram Reels created using a specific original audio.

The application collects Reel links, extracts Reel metadata, detects audio matches, stores records in PostgreSQL, and provides a Streamlit dashboard to view and manage the collected data.

## Key Features

- Collect Instagram Reel links using Playwright.
- Extract Reel metadata.
- Detect and manage original audio information.
- Store audio and Reel records in PostgreSQL.
- Export Reel metadata into CSV.
- Synchronize collected data with Google Sheets.
- Visualize tracking data through a Streamlit dashboard.

## Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3.10 |
| Web Automation | Playwright |
| Dashboard | Streamlit |
| Data Processing | Pandas |
| Data Visualization | Plotly |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Google Sheets Integration | gspread |
| Authentication | python-dotenv, Google Auth |

## Project Architecture

1. **Reel Collection:** Playwright collects Instagram Reel links.
2. **Metadata Extraction:** Reel metadata is extracted and saved.
3. **Audio Detection:** The application processes audio-related information and detects matches.
4. **Database Storage:** Audio and Reel records are stored in PostgreSQL.
5. **Data Synchronization:** Reel data can be synchronized with Google Sheets.
6. **Dashboard:** Streamlit displays the collected and processed information.

## Project Structure

```text
InstagramAudioTracker_Interview/
│
├── database/
│   ├── __init__.py
│   ├── connection.py
│   ├── crud.py
│   └── models.py
│
├── data/
│   └── audios/
│       └── audio_<id>/
│           ├── collected_reel_links.txt
│           ├── instagram_reels.csv
│           └── metadata.json
│
├── audio_detector.py
├── audio_manager.py
├── audio_workflow.py
├── reel_collector.py
├── extract_metadata.py
├── sync_google_sheets.py
├── streamlit_app.py
├── requirements.txt
├── .env
└── .gitignore
```

## Setup Instructions

### 1. Create Virtual Environment

```powershell
python -m venv .venv
```

### 2. Activate Environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file with the required database and application configuration.

### 5. Run Application

```powershell
python -m streamlit run streamlit_app.py
```

## Database

PostgreSQL is used for persistent storage.

Current database tables:

- `audios`
- `reels`
- `scan_history`

## Current Data Snapshot

- Original audio records: 1
- Reel records in PostgreSQL: 286
- Reel records in CSV: 286

## Important Note

Instagram access and data collection depend on browser availability, login status, and Instagram's access restrictions. The application uses browser automation rather than an official Instagram API.
