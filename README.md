# whoop-analysis

Fetches your personal WHOOP biometric data via the WHOOP Developer API and exports it to structured CSV files for analysis and visualization. Built with Python, OAuth 2.0, and paginated REST API calls.

---

## What it does

Authenticates with the WHOOP API using OAuth 2.0, then fetches your complete history across four data types — paginating through every available record — and saves each to a CSV:

| File | Contents |
|---|---|
| `whoop_cycles.csv` | Daily strain, avg/max heart rate, kilojoules |
| `whoop_recoveries.csv` | Recovery score, HRV, resting heart rate, SpO2, skin temp |
| `whoop_sleeps.csv` | Sleep stages, duration, performance, consistency, efficiency |
| `whoop_workouts.csv` | Per-workout strain, heart rate zones, distance, sport type |

Profile and body measurement data is saved to `whoop_profile.json`.

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Saun-JaySamuels/whoop-analysis.git
cd whoop-analysis
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create a WHOOP Developer app

1. Go to [developer.whoop.com](https://developer.whoop.com) and create an account
2. Create a new application
3. Set the redirect URI to `http://localhost:8000/callback`
4. Copy your **Client ID** and **Client Secret**

### 5. Set up your `.env` file

Create a `.env` file in the project root:

```
WHOOP_CLIENT_ID=your_client_id_here
WHOOP_CLIENT_SECRET=your_client_secret_here
```

This file is excluded from Git via `.gitignore` — never commit it.

---

## Usage

```bash
python whoop_data.py
```

A browser window will open asking you to log in to WHOOP and authorize the app. Once you approve, the script fetches all your data and saves the CSV files locally. Depending on how long you've had your WHOOP, this may take a few seconds.

---

## Output files

All output files are excluded from version control via `.gitignore`. They are generated locally and never committed to the repo.

```
whoop_cycles.csv
whoop_recoveries.csv
whoop_sleeps.csv
whoop_workouts.csv
whoop_profile.json
```

---

## Project structure

```
whoop-analysis/
├── whoop_data.py        # Main script — auth, fetch, export
├── whoop_auth.py        # Standalone auth helper (prints tokens)
├── requirements.txt     # Python dependencies
├── .gitignore           # Excludes data files, credentials, venv
└── README.md
```

---

## Dependencies

- [`requests`](https://pypi.org/project/requests/) — HTTP calls to the WHOOP API
- [`python-dotenv`](https://pypi.org/project/python-dotenv/) — loads credentials from `.env`

All other imports (`csv`, `json`, `os`, `webbrowser`, etc.) are Python standard library.

---

## Notes

- WHOOP's API returns a maximum of 25 records per request. The script handles pagination automatically and fetches your full history regardless of how many pages it takes.
- The API requires re-authentication each run (no refresh token persistence yet).
- Data is personal health information — keep your CSV files local and out of version control.
