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

# Get fresh token
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
print("Got token, fetching your data...\n")

# Fetch recovery data
headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
response = requests.get(
    "https://api.prod.whoop.com/developer/v2/cycle",
    headers=headers
)

data = response.json()
print("\n--- YOUR WHOOP DATA ---\n")
for record in data.get("records", []):
    score = record.get("score", {})
    date = record["start"][:10]
    strain = score.get("strain", 0)
    avg_hr = score.get("average_heart_rate", 0)
    print(f"Date: {date} | Strain: {round(strain, 1)} | Avg HR: {avg_hr}")