print("Starting WHOOP DATA fetch...")

import os
import requests
import webbrowser
import secrets
import csv
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("WHOOP_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/callback"
AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"

# AUTHENTICATION
state = secrets.token_urlsafe(16)
auth_params = {
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": "read:recovery read:cycles read:sleep read:workout read:profile read:body_measurement offline",
    "state": state,
}
auth_request = requests.Request("GET", AUTH_URL, params=auth_params).prepare()
webbrowser.open(auth_request.url)

auth_code = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        query = parse_qs(urlparse(self.path).query)
        auth_code = query.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Auth complete. You can close this tab.")
    def log_message(self, format, *args):
        pass

server = HTTPServer(("localhost", 8000), CallbackHandler)
print("Waiting for WHOOP login in your browser...")
server.handle_request()

token_response = requests.post(TOKEN_URL, data={
    "grant_type": "authorization_code",
    "code": auth_code,
    "redirect_uri": REDIRECT_URI,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
})

ACCESS_TOKEN = token_response.json().get("access_token")
print("Got token, fetching ALL your data...\n")

headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}


# Paginator
def fetch_all(endpoint):
    """Fetch every page from a WHOOP v1/v2 endpoint and return all records."""
    all_records = []
    next_token = None
    page = 1

    while True:
        print(f"  Fetching page {page}...")
        params = {"limit": 25}
        if next_token:
            params["nextToken"] = next_token

        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        records = data.get("records", [])
        all_records.extend(records)
        print(f"    Got {len(records)} records (total: {len(all_records)})")

        next_token = data.get("next_token")
        if not next_token:
            break
        page += 1

    return all_records


# Fetch profile
def fetch_profile():
    r = requests.get("https://api.prod.whoop.com/developer/v2/user/profile/basic", headers=headers)
    r.raise_for_status()
    return r.json()

def fetch_body_measurement():
    r = requests.get("https://api.prod.whoop.com/developer/v2/user/measurement/body", headers=headers)
    r.raise_for_status()
    return r.json()


# Fetch each dataset
print("Fetching cycles...")
cycles = fetch_all("https://api.prod.whoop.com/developer/v2/cycle")

print("\nFetching recoveries...")
recoveries = fetch_all("https://api.prod.whoop.com/developer/v2/recovery")

print("\nFetching sleeps...")
sleeps = fetch_all("https://api.prod.whoop.com/developer/v2/activity/sleep")

print("\nFetching workouts...")
workouts = fetch_all("https://api.prod.whoop.com/developer/v2/activity/workout")

print("\nFetching profile...")
profile = fetch_profile()

print("Fetching body measurements...")
body = fetch_body_measurement()


# Cycles CSV
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
print(f"\nSaved whoop_cycles.csv ({len(cycles)} records)")


# Recoveries CSV
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
print(f"Saved whoop_recoveries.csv ({len(recoveries)} records)")


# Sleeps CSV
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
print(f"Saved whoop_sleeps.csv ({len(sleeps)} records)")


# Workouts CSV
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
print(f"Saved whoop_workouts.csv ({len(workouts)} records)")


# Profile and body measurement JSON
with open("whoop_profile.json", "w") as f:
    json.dump({"profile": profile, "body_measurement": body}, f, indent=2)
print("Saved whoop_profile.json")


print("\n All done!")
print(f"  Cycles:     {len(cycles)}")
print(f"  Recoveries: {len(recoveries)}")
print(f"  Sleeps:     {len(sleeps)}")
print(f"  Workouts:   {len(workouts)}")