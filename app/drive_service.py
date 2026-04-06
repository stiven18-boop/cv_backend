import os
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/drive"]

FOLDERS = {
    "estandar": "18-ZSVYnNa8yT9ayy5V7kyXc4VexqEA3b",
    "mixta": "1SKEqWU49k2k6WSuavrLQtyTwxXqpUAoX"
}

# ── Cargar credenciales desde variable de entorno (Render) o archivo local ──
_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if _creds_json:
    _creds_info = json.loads(_creds_json)
    creds = service_account.Credentials.from_service_account_info(
        _creds_info, scopes=SCOPES
    )
else:
    # Solo para desarrollo local
    _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _FILE = os.path.join(_BASE, "utp-bot-egresados-b4982b2200ec.json")
    creds = service_account.Credentials.from_service_account_file(
        _FILE, scopes=SCOPES
    )