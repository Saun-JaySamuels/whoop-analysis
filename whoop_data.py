print("Starting WHOOP DATA fetch...")

import os
import requests
import webbrowser
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("WHOOP_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/callback"
AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"

# ---- LOGIN (unchanged) ----
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

# ---- NEW: FETCH ALL PAGES ----

headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

# We'll collect every record here instead of printing one page at a time
all_records = []

# "next_token" is like a bookmark — WHOOP gives you one at the end of each
# page so you can ask for the next page. We start with None (no bookmark yet).
next_token = None

page_number = 1

# "while True" means: keep looping forever UNTIL we say "break"
while True:
    print(f"Fetching page {page_number}...")

    # Build the request parameters.
    # We always ask for 25 records at a time (the max WHOOP allows).
    params = {"limit": 25}

    # If we have a bookmark from the previous page, include it so WHOOP
    # knows where to continue from.
    if next_token:
        params["nextToken"] = next_token

    response = requests.get(
        "https://api.prod.whoop.com/developer/v2/cycle",
        headers=headers,
        params=params        # <-- NEW: pass the pagination parameters
    )

    data = response.json()

    # Grab the records from this page and add them to our master list.
    # (extend is like append, but adds a whole list at once)
    records_this_page = data.get("records", [])
    all_records.extend(records_this_page)

    print(f"  Got {len(records_this_page)} records (total so far: {len(all_records)})")

    # WHOOP includes a "next_token" field when there are more pages.
    # If it's missing or empty, we've reached the last page — stop looping.
    next_token = data.get("next_token")
    if not next_token:
        print("No more pages — all data fetched!")
        break   # Exit the while loop

    page_number += 1

import csv

output_file = "whoop_data.csv"

with open(output_file, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Date", "Strain", "Avg HR", "Kilojoule"])

    for record in all_records:
        score = record.get("score", {})
        date = record["start"][:10]
        strain = score.get("strain", 0)
        avg_hr = score.get("average_heart_rate", 0)
        kilojoule = score.get("kilojoule", 0)
        writer.writerow([date, round(strain, 1), avg_hr, round(kilojoule, 2)])

print(f"\nDone! Saved to {output_file} — {len(all_records)} total records")