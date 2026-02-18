from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.drive_service import descargar_archivos
from app.database import Base, engine
from app.processor import procesar_archivos
from dashboard.dashboard import router as dashboard_router

app = FastAPI()

# Crear tablas en la base de datos
Base.metadata.create_all(bind=engine)

# Incluir las rutas del dashboard
app.include_router(dashboard_router)

# Ruta raíz
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <h1>Servidor funcionando correctamente</h1>
    <p>Ir al <a href='/dashboard'>Dashboard</a></p>
    <p>Documentación API: <a href='/docs'>/docs</a></p>
    """

# Endpoint para actualizar información
@app.post("/actualizar")
def actualizar():
    descargar_archivos()
    procesar_archivos()
    return {"mensaje": "Información actualizada correctamente"}
