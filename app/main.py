from fastapi import FastAPI
from app.drive_service import descargar_archivos
from app.database import Base, engine
from app.processor import procesar_archivos

app = FastAPI()
Base.metadata.create_all(bind=engine)

@app.post("/actualizar")
def actualizar():
    descargar_archivos()
    procesar_archivos()
    return {"mensaje": "Información actualizada correctamente"}
