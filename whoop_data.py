"""WHOOP data export script — fetches all historical data from the WHOOP v2 API."""

import os
import csv
import json
import secrets
import time
import webbrowser
import requests
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

CLIENT_ID     = os.getenv("WHOOP_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET")
REDIRECT_URI  = "http://localhost:8000/callback"
AUTH_URL      = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL     = "https://api.prod.whoop.com/oauth/oauth2/token"
BASE_URL      = "https://api.prod.whoop.com/developer/v2"
TOKEN_FILE    = ".whoop_tokens.json"


# ─── TOKEN PERSISTENCE ────────────────────────────────────────────────────────

def load_saved_tokens():
    """Load tokens from TOKEN_FILE if it exists and is readable."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_tokens(tokens):
    """Persist access and refresh tokens to TOKEN_FILE for future runs."""
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token":  tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
        }, f, indent=2)


def try_refresh_token(refresh_token):
    """Attempt to exchange a refresh token for a new access token.

    Returns the token response dict on success, or None if the refresh fails.
    """
    try:
        r = requests.post(TOKEN_URL, data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }, timeout=30)
        if r.ok and r.json().get("access_token"):
            return r.json()
        print(f"  Token refresh failed (HTTP {r.status_code}) — falling back to browser login.")
        return None
    except requests.RequestException as e:
        print(f"  Token refresh error: {e} — falling back to browser login.")
        return None


def browser_login():
    """Perform the full OAuth2 browser-based login flow.

    Opens a browser to the WHOOP authorisation page, waits for the callback
    on localhost:8000, then exchanges the authorisation code for tokens.
    Returns the full token response dict.
    """
    state = secrets.token_urlsafe(16)
    auth_params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         "read:recovery read:cycles read:sleep read:workout "
                         "read:profile read:body_measurement offline",
        "state":         state,
    }
    auth_request = requests.Request("GET", AUTH_URL, params=auth_params).prepare()
    webbrowser.open(auth_request.url)

    # Use a list as a mutable container so the nested class can write to it
    auth_code_holder = [None]

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            auth_code_holder[0] = query.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Auth complete. You can close this tab.")

        def log_message(self, format, *args):
            pass

    print("Waiting for WHOOP login in your browser...")
    server = HTTPServer(("localhost", 8000), CallbackHandler)
    server.handle_request()

    token_response = requests.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "code":          auth_code_holder[0],
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }, timeout=30)
    token_response.raise_for_status()
    return token_response.json()


def get_access_token():
    """Return a valid access token, using saved tokens when possible.

    Order of operations:
    1. Load saved tokens from TOKEN_FILE.
    2. If a refresh token is present, try to get a fresh access token silently.
    3. If that fails (or no tokens exist), fall back to the full browser login.
    4. Save the resulting tokens so the next run can skip the browser step.
    """
    saved = load_saved_tokens()

    if saved and saved.get("refresh_token"):
        print("Found saved refresh token — attempting silent refresh...")
        tokens = try_refresh_token(saved["refresh_token"])
        if tokens:
            save_tokens(tokens)
            print("Token refreshed — no browser login needed.")
            return tokens["access_token"]

    print("Performing full browser-based login...")
    tokens = browser_login()
    save_tokens(tokens)
    print("Login successful. Tokens saved for future runs.")
    return tokens["access_token"]


# ─── HTTP HELPERS ─────────────────────────────────────────────────────────────

def api_get_with_retry(url, headers, params=None, max_retries=3):
    """GET request with exponential backoff for transient errors (429, 5xx).

    On a 429 the Retry-After header is respected if present.
    Raises the last exception or calls raise_for_status() after all retries.
    """
    delay = 2
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            if attempt == max_retries:
                raise
            print(f"    Network error (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2
            continue

        if response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", delay))
            else:
                wait = delay
            print(f"    HTTP {response.status_code} (attempt {attempt + 1}). Retrying in {wait}s...")
            time.sleep(wait)
            delay *= 2
            continue

        return response

    return response  # last attempt — caller checks raise_for_status()


def fetch_all(endpoint, headers):
    """Fetch every page from a WHOOP v2 paginated endpoint.

    Uses cursor-based pagination via nextToken. Each page request goes through
    the retry logic in api_get_with_retry.
    """
    all_records = []
    next_token = None
    page = 1

    while True:
        print(f"  Page {page}...", end=" ", flush=True)
        params = {"limit": 25}
        if next_token:
            params["nextToken"] = next_token

        response = api_get_with_retry(endpoint, headers, params=params)
        response.raise_for_status()
        data = response.json()

        records = data.get("records", [])
        all_records.extend(records)
        print(f"{len(records)} records (total so far: {len(all_records)})")

        next_token = data.get("next_token")
        if not next_token:
            break
        page += 1

    return all_records


def fetch_single(url, headers):
    """Fetch a single non-paginated endpoint with retry logic."""
    response = api_get_with_retry(url, headers)
    response.raise_for_status()
    return response.json()


# ─── CSV WRITERS ──────────────────────────────────────────────────────────────

def write_cycles_csv(cycles):
    """Write cycles records to whoop_cycles.csv."""
    with open("whoop_cycles.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "cycle_id", "user_id", "start", "end", "timezone_offset",
            "score_state",
            "strain", "avg_heart_rate", "max_heart_rate", "kilojoule",
            "percent_recorded", "during_latest_workout",
        ])
        for r in cycles:
            s = r.get("score") or {}
            writer.writerow([
                r.get("id"), r.get("user_id"), r.get("start"), r.get("end"),
                r.get("timezone_offset"), r.get("score_state"),
                s.get("strain"), s.get("average_heart_rate"), s.get("max_heart_rate"),
                s.get("kilojoule"), s.get("percent_recorded"),
                s.get("during_latest_workout"),
            ])


def write_recoveries_csv(recoveries):
    """Write recoveries records to whoop_recoveries.csv."""
    with open("whoop_recoveries.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "cycle_id", "sleep_id", "user_id", "created_at", "updated_at",
            "score_state",
            "recovery_score", "resting_heart_rate", "hrv_rmssd_milli",
            "spo2_percentage", "skin_temp_celsius",
        ])
        for r in recoveries:
            s = r.get("score") or {}
            writer.writerow([
                r.get("cycle_id"), r.get("sleep_id"), r.get("user_id"),
                r.get("created_at"), r.get("updated_at"), r.get("score_state"),
                s.get("recovery_score"), s.get("resting_heart_rate"),
                s.get("hrv_rmssd_milli"), s.get("spo2_percentage"),
                s.get("skin_temp_celsius"),
            ])


def write_sleeps_csv(sleeps):
    """Write sleeps records to whoop_sleeps.csv."""
    with open("whoop_sleeps.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "sleep_id", "user_id", "start", "end", "timezone_offset",
            "nap", "score_state",
            "total_in_bed_time_milli", "total_awake_time_milli",
            "total_no_data_time_milli", "total_light_sleep_time_milli",
            "total_slow_wave_sleep_time_milli", "total_rem_sleep_time_milli",
            "sleep_cycle_count", "disturbance_count",
            "baseline_milli", "need_from_strain_milli",
            "need_from_sleep_debt_milli", "need_from_recent_strain_milli",
            "need_from_recent_nap_milli", "sleep_needed_milli",
            "respiratory_rate", "sleep_performance_percentage",
            "sleep_consistency_percentage", "sleep_efficiency_percentage",
        ])
        for r in sleeps:
            s = r.get("score") or {}
            sn = s.get("sleep_needed") or {}
            writer.writerow([
                r.get("id"), r.get("user_id"), r.get("start"), r.get("end"),
                r.get("timezone_offset"), r.get("nap"), r.get("score_state"),
                s.get("total_in_bed_time_milli"), s.get("total_awake_time_milli"),
                s.get("total_no_data_time_milli"), s.get("total_light_sleep_time_milli"),
                s.get("total_slow_wave_sleep_time_milli"), s.get("total_rem_sleep_time_milli"),
                s.get("sleep_cycle_count"), s.get("disturbance_count"),
                sn.get("baseline_milli"), sn.get("need_from_strain_milli"),
                sn.get("need_from_sleep_debt_milli"), sn.get("need_from_recent_strain_milli"),
                sn.get("need_from_recent_nap_milli"), sn.get("sleep_needed_milli"),
                s.get("respiratory_rate"), s.get("sleep_performance_percentage"),
                s.get("sleep_consistency_percentage"), s.get("sleep_efficiency_percentage"),
            ])


def write_workouts_csv(workouts):
    """Write workouts records to whoop_workouts.csv."""
    with open("whoop_workouts.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "workout_id", "user_id", "start", "end", "timezone_offset",
            "sport_id", "score_state",
            "strain", "avg_heart_rate", "max_heart_rate", "kilojoule",
            "percent_recorded", "distance_meter", "altitude_gain_meter",
            "altitude_change_meter",
            "zone_zero_milli", "zone_one_milli", "zone_two_milli",
            "zone_three_milli", "zone_four_milli", "zone_five_milli",
        ])
        for r in workouts:
            s = r.get("score") or {}
            z = s.get("zone_duration") or {}
            writer.writerow([
                r.get("id"), r.get("user_id"), r.get("start"), r.get("end"),
                r.get("timezone_offset"), r.get("sport_id"), r.get("score_state"),
                s.get("strain"), s.get("average_heart_rate"), s.get("max_heart_rate"),
                s.get("kilojoule"), s.get("percent_recorded"),
                s.get("distance_meter"), s.get("altitude_gain_meter"),
                s.get("altitude_change_meter"),
                z.get("zone_zero_milli"), z.get("zone_one_milli"), z.get("zone_two_milli"),
                z.get("zone_three_milli"), z.get("zone_four_milli"), z.get("zone_five_milli"),
            ])


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def ts():
    """Return the current wall-clock time as HH:MM:SS for progress output."""
    return datetime.now().strftime("%H:%M:%S")


print("Starting WHOOP data fetch...")

# Authenticate — uses saved tokens if available, otherwise opens the browser
ACCESS_TOKEN = get_access_token()
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
print(f"[{ts()}] Authentication complete.\n")

# Each entry: (display name, API URL, CSV writer function, output filename)
ENDPOINTS = [
    ("cycles",     f"{BASE_URL}/cycle",            write_cycles_csv,     "whoop_cycles.csv"),
    ("recoveries", f"{BASE_URL}/recovery",         write_recoveries_csv, "whoop_recoveries.csv"),
    ("sleeps",     f"{BASE_URL}/activity/sleep",   write_sleeps_csv,     "whoop_sleeps.csv"),
    ("workouts",   f"{BASE_URL}/activity/workout", write_workouts_csv,   "whoop_workouts.csv"),
]

# ─── FETCH AND WRITE EACH PAGINATED ENDPOINT ──────────────────────────────────

fetch_results = {}  # name -> {"count": int, "file": str or None, "error": str or None}

for name, url, writer_fn, filename in ENDPOINTS:
    print(f"[{ts()}] Fetching {name}...")
    error = None
    records = []
    try:
        records = fetch_all(url, HEADERS)
        if len(records) == 0:
            print(f"  WARNING: 0 records returned for {name}.")
        writer_fn(records)
    except requests.HTTPError as e:
        resp = e.response
        print(f"  ERROR fetching {name}: HTTP {resp.status_code}")
        print(f"  Response body: {resp.text[:500]}")
        error = f"HTTP {resp.status_code}"
        filename = None
    except Exception as e:
        print(f"  ERROR fetching {name}: {e}")
        error = str(e)
        filename = None

    fetch_results[name] = {
        "count": len(records),
        "file":  filename if error is None else None,
        "error": error,
    }
    print()

# ─── FETCH PROFILE (NON-PAGINATED) ────────────────────────────────────────────

print(f"[{ts()}] Fetching profile and body measurements...")
profile_error = None
profile_saved = False
try:
    profile = fetch_single(f"{BASE_URL}/user/profile/basic", HEADERS)
    body    = fetch_single(f"{BASE_URL}/user/measurement/body", HEADERS)
    with open("whoop_profile.json", "w") as f:
        json.dump({"profile": profile, "body_measurement": body}, f, indent=2)
    profile_saved = True
except requests.HTTPError as e:
    resp = e.response
    print(f"  ERROR fetching profile: HTTP {resp.status_code}")
    print(f"  Response body: {resp.text[:500]}")
    profile_error = f"HTTP {resp.status_code}"
except Exception as e:
    print(f"  ERROR fetching profile: {e}")
    profile_error = str(e)

# ─── SUMMARY TABLE ────────────────────────────────────────────────────────────

print("\n" + "=" * 68)
print(f"  {'ENDPOINT':<14} {'RECORDS':>8}  {'FILE SAVED':<26}  STATUS")
print("  " + "-" * 64)

for name, result in fetch_results.items():
    file_str   = result["file"] or "—"
    status_str = "OK" if result["error"] is None else f"FAILED: {result['error']}"
    print(f"  {name:<14} {result['count']:>8}  {file_str:<26}  {status_str}")

profile_file   = "whoop_profile.json" if profile_saved else "—"
profile_status = "OK" if profile_error is None else f"FAILED: {profile_error}"
print(f"  {'profile':<14} {'—':>8}  {profile_file:<26}  {profile_status}")

print("=" * 68)

failed = [n for n, r in fetch_results.items() if r["error"]] + (["profile"] if profile_error else [])
if failed:
    print(f"\n  WARNING: {len(failed)} endpoint(s) failed: {', '.join(failed)}")
else:
    print("\n  All done — all data fetched and saved successfully.")
