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

tokens = token_response.json()
print("\nSuccess! Your tokens:")
print("Access Token:", tokens.get("access_token"))
print("Refresh Token:", tokens.get("refresh_token"))