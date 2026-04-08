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

def descargar_archivos():

    service = build("drive", "v3", credentials=creds)

    for nombre_carpeta, folder_id in FOLDERS.items():

        print(f"\nProcesando carpeta: {nombre_carpeta}")

        carpeta_local = os.path.join("descargas", nombre_carpeta)
        os.makedirs(carpeta_local, exist_ok=True)

        page_token = None

        while True:

            resultados = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name)",
                pageToken=page_token
            ).execute()

            archivos = resultados.get("files", [])

            print(f"Archivos encontrados en esta página: {len(archivos)}")

            for archivo in archivos:

                ruta_archivo = os.path.join(carpeta_local, archivo["name"])

                # Evitar descargar si ya existe
                if os.path.exists(ruta_archivo):
                    continue

                request = service.files().get_media(fileId=archivo["id"])

                with open(ruta_archivo, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)

                    done = False
                    while not done:
                        status, done = downloader.next_chunk()

                print(f"[DESCARGADO] {archivo['name']}")

            page_token = resultados.get("nextPageToken")

            if not page_token:
                break