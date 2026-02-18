import os
import pdfplumber
import re
from app.database import SessionLocal
from app.models import Candidato


def extraer_email(texto):
    match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", texto)
    return match.group(0) if match else None


def procesar_archivos():

    db = SessionLocal()
    carpeta = "descargas"

    insertados = 0
    omitidos = 0

    try:
        for archivo in os.listdir(carpeta):

            if not archivo.lower().endswith(".pdf"):
                continue

            ruta = os.path.join(carpeta, archivo)

            with pdfplumber.open(ruta) as pdf:
                texto = ""
                for pagina in pdf.pages:
                    texto += pagina.extract_text() or ""

            email = extraer_email(texto)

            # 🔎 Validar duplicado por email
            if email:
                existente = db.query(Candidato).filter(Candidato.email == email).first()
                if existente:
                    omitidos += 1
                    continue

            candidato = Candidato(
                nombre=archivo.replace(".pdf", ""),
                email=email,
                telefono="Pendiente",
                habilidades="Pendiente",
                experiencia="Pendiente"
            )

            db.add(candidato)
            insertados += 1

        db.commit()

    except Exception as e:
        db.rollback()
        print("Error:", e)

    finally:
        db.close()

    return {
        "insertados": insertados,
        "omitidos": omitidos
    }
