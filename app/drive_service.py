from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import os
import io

credentials_info = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDERS= {"Estandar":"18-ZSVYnNa8yT9ayy5V7kyXc4VexqEA3b",
             "Mixta": "1SKEqWU49k2k6WSuavrLQtyTwxXqpUAoX"}

def descargar_archivos():  # Función reutilizable

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info
    )

    service = build('drive', 'v3', credentials=credentials)

    for nombre_carpeta, FOLDER_ID in FOLDERS.items():

        resultados = service.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed = false",
            fields="files(id, name)"
        ).execute()

        archivos = resultados.get("files", [])

        carpeta_local = os.path.join("descargas", nombre_carpeta)
        os.makedirs(carpeta_local, exist_ok=True)

        for archivo in archivos:

            request = service.files().get_media(fileId=archivo["id"])

            ruta_archivo = os.path.join(carpeta_local, archivo["name"])

            with open(ruta_archivo, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)

                done = False
                while not done:
                    status, done = downloader.next_chunk()