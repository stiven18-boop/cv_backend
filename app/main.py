from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
import bcrypt
from datetime import datetime
import os
import json
import numpy as np
import unicodedata
import re
import tempfile
import zipfile
import io
import asyncio
from fastapi.responses import StreamingResponse
from docx2pdf import convert
from app.database import Base, engine, SessionLocal
from app.models import Candidato, Usuario
from app.drive_service import descargar_archivos
from app.processor import procesar_archivos

from sentence_transformers import SentenceTransformer

# ===============================
# INICIALIZACIÓN
# ===============================

app = FastAPI()
Base.metadata.create_all(bind=engine)
_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

UMBRAL_MINIMO = 0.10

# ── Hashing de contraseñas (bcrypt directo, sin passlib) ──
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ===============================
# CREAR USUARIO ADMIN POR DEFECTO
# ===============================

def init_usuario_admin():
    """
    Al arrancar, si no existe ningún usuario, crea admin/admin123.
    Cambia la contraseña después del primer inicio de sesión.
    """
    db = SessionLocal()
    try:
        if db.query(Usuario).count() == 0:
            hashed = hash_password("admin123")
            admin  = Usuario(
                username = "admin",
                password = hashed,
                activo   = True,
                creado   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            db.add(admin)
            db.commit()
            print("=" * 55)
            print("✅  Usuario admin creado automáticamente.")
            print("    Usuario:    admin")
            print("    Contraseña: admin123")
            print("⚠️   Cámbiala con POST /auth/cambiar-password")
            print("=" * 55)
    finally:
        db.close()


# Ejecutar al iniciar
init_usuario_admin()


# ===============================
# ESTADO DEL PROCESO EN BACKGROUND
# ===============================

estado_actualizacion = {
    "en_proceso":       False,
    "ultimo_resultado": None,
    "error":            None
}


def ejecutar_actualizacion():
    global estado_actualizacion
    try:
        estado_actualizacion["en_proceso"]       = True
        estado_actualizacion["error"]            = None
        estado_actualizacion["ultimo_resultado"] = None

        descargar_archivos()
        resultado = procesar_archivos()

        estado_actualizacion["ultimo_resultado"] = resultado
    except Exception as e:
        estado_actualizacion["error"] = str(e)
    finally:
        estado_actualizacion["en_proceso"] = False


# ===============================
# SIMILITUD COSENO
# ===============================

def similitud_coseno(v1, v2):
    v1    = np.array(v1)
    v2    = np.array(v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


# ==========================
#
# =====
# UTILIDADES DE TEXTO
# ===============================

def normalizar(texto):
    """Convierte a minúsculas y elimina tildes para comparación robusta."""
    if not texto:
        return ""
    texto = texto.lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

def keywords_de(texto):
    """Extrae palabras clave significativas de un texto de búsqueda."""
    if not texto:
        return []
    stopwords = {"de", "en", "el", "la", "los", "las", "un", "una", "y", "o",
                 "con", "para", "por", "del", "al", "como", "que", "se", "su"}
    return [
        normalizar(w.strip(",.;:"))
        for w in texto.split()
        if len(w) > 3 and w.lower() not in stopwords
    ]

def texto_relevante_candidato(c):
    """
    Construye el texto de búsqueda SOLO desde campos estructurados.
    Excluye texto_completo para evitar falsos positivos.
    """
    partes = [
        c.perfil                   or "",
        c.experiencia              or "",
        c.habilidades              or "",
        c.formacion_complementaria or "",
    ]
    return normalizar(" ".join(partes))

def tiene_coincidencia_lexica(texto_cv_norm, keywords, frase_original):
    if not keywords:
        return True

    frase_norm = normalizar(frase_original)

    # 1. Frase exacta normalizada ("ingeniero electronico")
    if frase_norm in texto_cv_norm:
        return True

    # 2. Variaciones de la frase con palabras adyacentes (máx 2 palabras de distancia)
    if len(keywords) >= 2:
        for i in range(len(keywords)):
            for j in range(len(keywords)):
                if i == j:
                    continue
                # Buscar kw[i] seguida de kw[j] con hasta 2 palabras entre ellas
                patron = r'\b' + re.escape(keywords[i]) + r'(?:\s+\w+){0,2}\s+' + re.escape(keywords[j]) + r'\b'
                if re.search(patron, texto_cv_norm):
                    return True
        # Si ninguna combinación adyacente encontrada → rechazar
        return False

    # 3. Si solo hay 1 keyword, debe estar presente
    return keywords[0] in texto_cv_norm


# ================================================================
# ██████╗  AUTH
# ================================================================

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class CambiarPasswordRequest(BaseModel):
    username:         str
    password_actual:  str
    password_nueva:   str


@app.post("/auth/login")
def login(data: LoginRequest):
    """
    Verifica credenciales.
    Retorna 200 + {username} si son correctas.
    Retorna 401 si son incorrectas o el usuario está inactivo.
    """
    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(
            Usuario.username == data.username.strip()
        ).first()

        if not usuario:
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

        if not usuario.activo:
            raise HTTPException(status_code=401, detail="Usuario inactivo. Contacta al administrador.")

        if not verify_password(data.password, usuario.password):
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

        return {"status": "ok", "username": usuario.username}
    finally:
        db.close()


@app.post("/auth/register")
def register(data: RegisterRequest):
    """
    Registra un nuevo usuario.
    Retorna 400 si el username ya existe o la contraseña es muy corta.
    """
    if len(data.password) < 6:
        raise HTTPException(
            status_code=400,
            detail="La contraseña debe tener al menos 6 caracteres."
        )

    db = SessionLocal()
    try:
        existente = db.query(Usuario).filter(
            Usuario.username == data.username.strip()
        ).first()

        if existente:
            raise HTTPException(status_code=400, detail="El nombre de usuario ya existe.")

        nuevo = Usuario(
            username = data.username.strip(),
            password = hash_password(data.password),
            activo   = True,
            creado   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.add(nuevo)
        db.commit()
        return {"status": "ok", "username": nuevo.username}
    finally:
        db.close()


@app.post("/auth/cambiar-password")
def cambiar_password(data: CambiarPasswordRequest):
    """Permite a un usuario cambiar su propia contraseña."""
    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(
            Usuario.username == data.username.strip()
        ).first()

        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")

        if not verify_password(data.password_actual, usuario.password):
            raise HTTPException(status_code=401, detail="Contraseña actual incorrecta.")

        if len(data.password_nueva) < 6:
            raise HTTPException(
                status_code=400,
                detail="La contraseña nueva debe tener al menos 6 caracteres."
            )

        usuario.password = hash_password(data.password_nueva)
        db.commit()
        return {"status": "ok", "mensaje": "Contraseña actualizada correctamente."}
    finally:
        db.close()


@app.get("/auth/usuarios")
def listar_usuarios():
    """Lista todos los usuarios (sin contraseñas)."""
    db = SessionLocal()
    try:
        usuarios = db.query(Usuario).all()
        return [
            {
                "id":       u.id,
                "username": u.username,
                "activo":   u.activo,
                "creado":   u.creado
            }
            for u in usuarios
        ]
    finally:
        db.close()


# ================================================================
# ██████╗  CANDIDATOS
# ================================================================

@app.post("/actualizar")
def actualizar(background_tasks: BackgroundTasks):
    if estado_actualizacion["en_proceso"]:
        return {"status": "en_proceso", "mensaje": "Ya hay una actualización en curso."}
    background_tasks.add_task(ejecutar_actualizacion)
    return {"status": "iniciado", "mensaje": "Actualización iniciada."}


@app.get("/actualizar/estado")
def estado():
    if estado_actualizacion["en_proceso"]:
        return {"status": "en_proceso"}
    if estado_actualizacion["error"]:
        return {"status": "error", "detalle": estado_actualizacion["error"]}
    if estado_actualizacion["ultimo_resultado"]:
        return {"status": "completado", **estado_actualizacion["ultimo_resultado"]}
    return {"status": "sin_ejecutar"}


@app.get("/buscar")
def buscar(
    titulo:      Optional[str] = Query(None),
    experiencia: Optional[str] = Query(None),
    habilidad:   Optional[str] = Query(None),
    universidad: Optional[str] = Query(None),
    nivel:       Optional[str] = Query(None),
    top_k:       int   = 1000,
    umbral:      float = UMBRAL_MINIMO
):
    db: Session = SessionLocal()
    try:
        if not any([titulo, experiencia, habilidad, universidad, nivel]):
            return {"error": "Debes enviar al menos un parámetro."}

        # ── Pre-filtro SQL por universidad y nivel ──
        query_db = db.query(Candidato)

        if universidad and universidad.strip():
            query_db = query_db.filter(
                Candidato.educacion.ilike(f"%{universidad.strip()}%")
            )

        if nivel and nivel.strip():
            nivel_keywords = {
                "Bachiller":              ["bachiller", "bachillerato", "secundaria"],
                "Técnico":                ["técnico", "tecnico"],
                "Tecnólogo":              ["tecnólogo", "tecnologo", "tecnología", "tecnologia"],
                "Profesional / Pregrado": ["profesional", "pregrado", "ingeniero", "licenciado",
                                           "administrador", "contador", "economista", "abogado",
                                           "médico", "arquitecto"],
                "Especialización":        ["especialización", "especializacion", "especialista"],
                "Maestría / Magíster":    ["maestría", "maestria", "magíster", "magister", "msc"],
                "Doctorado / PhD":        ["doctorado", "doctor", "phd"],
            }
            kws = nivel_keywords.get(nivel, [nivel.lower()])
            query_db = query_db.filter(
                or_(*[Candidato.educacion.ilike(f"%{kw}%") for kw in kws])
            )

        candidatos = query_db.all()
        if not candidatos:
            return []

        solo_filtros_academicos = not any([titulo, experiencia, habilidad])

        if solo_filtros_academicos:
            return [
                {
                    "id":          c.id,
                    "nombre":      c.nombre,
                    "archivo":     c.nombre_archivo,
                    "perfil":      c.perfil      or "",
                    "experiencia": c.experiencia or "",
                    "educacion":   c.educacion   or "",
                    "habilidades": (
                        c.habilidades if isinstance(c.habilidades, str)
                        else ", ".join(c.habilidades) if isinstance(c.habilidades, list)
                        else ""
                    ),
                    "formacion_complementaria": c.formacion_complementaria or "",
                    "score": 1.0
                }
                for c in candidatos
            ]
        # Al inicio de la función donde se usan, agrega:
        model = get_model()

        # Luego reemplaza embedding_model.encode por model.encode
        q_titulo = model.encode(f"Cargo o título profesional: {titulo}").tolist() if titulo else None
        q_experiencia = model.encode(f"Experiencia laboral en: {experiencia}").tolist() if experiencia else None
        q_habilidad = model.encode(f"Habilidades y competencias: {habilidad}").tolist() if habilidad else None
        # ── Keywords normalizadas para filtro léxico ──
        kw_titulo      = keywords_de(titulo)
        kw_experiencia = keywords_de(experiencia)
        kw_habilidad   = keywords_de(habilidad)

        resultados = []

        for c in candidatos:
            if not c.embedding:
                continue
            try:
                emb_general = json.loads(c.embedding)
            except Exception:
                continue

            # Texto normalizado SOLO de campos estructurados
            texto_cv = texto_relevante_candidato(c)

            # ── FILTRO LÉXICO ESTRICTO ──
            # Cada campo solicitado DEBE aparecer en los campos estructurados del CV.
            # Se normalizan tildes para no perder coincidencias válidas.
            if titulo and not tiene_coincidencia_lexica(texto_cv, kw_titulo, titulo):
                continue
            if experiencia and not tiene_coincidencia_lexica(texto_cv, kw_experiencia, experiencia):
                continue
            if habilidad and not tiene_coincidencia_lexica(texto_cv, kw_habilidad, habilidad):
                continue

            # ── Score semántico (para ordenar resultados) ──
            scores_campo = []
            if q_titulo      is not None:
                scores_campo.append(similitud_coseno(q_titulo,      emb_general))
            if q_experiencia is not None:
                scores_campo.append(similitud_coseno(q_experiencia, emb_general))
            if q_habilidad   is not None:
                scores_campo.append(similitud_coseno(q_habilidad,   emb_general))

            score_final = sum(scores_campo) / len(scores_campo) if scores_campo else 0.0

            resultados.append({
                "id":          c.id,
                "nombre":      c.nombre,
                "archivo":     c.nombre_archivo,
                "perfil":      c.perfil      or "",
                "experiencia": c.experiencia or "",
                "educacion":   c.educacion   or "",
                "habilidades": (
                    c.habilidades if isinstance(c.habilidades, str)
                    else ", ".join(c.habilidades) if isinstance(c.habilidades, list)
                    else ""
                ),
                "formacion_complementaria": c.formacion_complementaria or "",
                "score": round(score_final, 4)
            })

        resultados.sort(key=lambda x: x["score"], reverse=True)
        return resultados

    finally:
        db.close()


@app.get("/buscar-texto")
def buscar_texto(
    termino:     str,
    universidad: Optional[str] = Query(None),
    nivel:       Optional[str] = Query(None),
):
    db: Session = SessionLocal()
    try:
        if not termino or not termino.strip():
            return {"error": "El término no puede estar vacío."}

        termino = termino.strip()

        # Buscar SOLO en campos estructurados, NO en texto_completo
        query_db = db.query(Candidato).filter(
            or_(
                Candidato.perfil.ilike(f"%{termino}%"),
                Candidato.experiencia.ilike(f"%{termino}%"),
                Candidato.educacion.ilike(f"%{termino}%"),
                Candidato.habilidades.ilike(f"%{termino}%"),
                Candidato.formacion_complementaria.ilike(f"%{termino}%"),
            )
        )

        if universidad and universidad.strip():
            query_db = query_db.filter(
                Candidato.educacion.ilike(f"%{universidad.strip()}%")
            )

        if nivel and nivel.strip():
            nivel_keywords = {
                "Bachiller":              ["bachiller", "bachillerato", "secundaria"],
                "Técnico":                ["técnico", "tecnico"],
                "Tecnólogo":              ["tecnólogo", "tecnologo", "tecnología", "tecnologia"],
                "Profesional / Pregrado": ["profesional", "pregrado", "ingeniero", "licenciado",
                                           "administrador", "contador", "economista", "abogado",
                                           "médico", "arquitecto"],
                "Especialización":        ["especialización", "especializacion", "especialista"],
                "Maestría / Magíster":    ["maestría", "maestria", "magíster", "magister", "msc"],
                "Doctorado / PhD":        ["doctorado", "doctor", "phd"],
            }
            kws = nivel_keywords.get(nivel, [nivel.lower()])
            query_db = query_db.filter(
                or_(*[Candidato.educacion.ilike(f"%{kw}%") for kw in kws])
            )

        resultados = query_db.all()

        if not resultados:
            return []

        return [
            {
                "id":          c.id,
                "nombre":      c.nombre,
                "archivo":     c.nombre_archivo,
                "perfil":      c.perfil      or "",
                "experiencia": c.experiencia or "",
                "educacion":   c.educacion   or "",
                "habilidades": (
                    c.habilidades if isinstance(c.habilidades, str)
                    else ", ".join(c.habilidades) if isinstance(c.habilidades, list)
                    else ""
                ),
                "formacion_complementaria": c.formacion_complementaria or "",
            }
            for c in resultados
        ]
    finally:
        db.close()


@app.get("/candidatos")
def listar_candidatos(skip: int = 0, limit: int = 50):
    db: Session = SessionLocal()
    try:
        total      = db.query(Candidato).count()
        candidatos = db.query(Candidato).offset(skip).limit(limit).all()
        return {
            "total": total,
            "candidatos": [
                {
                    "id":                c.id,
                    "nombre":            c.nombre,
                    "tiene_perfil":      bool(c.perfil),
                    "tiene_experiencia": bool(c.experiencia),
                    "tiene_educacion":   bool(c.educacion),
                    "tiene_habilidades": bool(c.habilidades),
                    "tiene_embedding":   bool(c.embedding),
                }
                for c in candidatos
            ]
        }
    finally:
        db.close()


@app.get("/candidato/{candidato_id}")
def ver_candidato(candidato_id: int):
    db: Session = SessionLocal()
    try:
        c = db.query(Candidato).filter(Candidato.id == candidato_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Candidato no encontrado.")
        return {
            "id":             c.id,
            "nombre":         c.nombre,
            "perfil":         c.perfil         or "",
            "experiencia":    c.experiencia    or "",
            "educacion":      c.educacion      or "",
            "habilidades":    c.habilidades    or "",
            "formacion_complementaria": c.formacion_complementaria or "",
            "texto_completo": c.texto_completo or "",
        }
    finally:
        db.close()


@app.get("/descargar/{candidato_id}")
def descargar(candidato_id: int):
    db: Session = SessionLocal()
    try:
        candidato = db.query(Candidato).filter(Candidato.id == candidato_id).first()
        if not candidato:
            raise HTTPException(status_code=404, detail="Candidato no encontrado.")

        for root, dirs, files in os.walk("descargas"):
            for file in files:
                if file == candidato.nombre_archivo:
                    ruta_original = os.path.join(root, file)
                    ext = os.path.splitext(file)[1].lower()

                    # Si es Word → convertir a PDF en memoria temporal
                    if ext in (".docx", ".doc"):
                        nombre_pdf = os.path.splitext(file)[0] + ".pdf"
                        ruta_pdf   = os.path.join(tempfile.gettempdir(), nombre_pdf)
                        try:
                            convert(ruta_original, ruta_pdf)
                            return FileResponse(
                                path       = ruta_pdf,
                                filename   = nombre_pdf,
                                media_type = "application/pdf"
                            )
                        except Exception as e:
                            # Si la conversión falla, entregar el Word original
                            return FileResponse(
                                path       = ruta_original,
                                filename   = file,
                                media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            )

                    # PDF u otro formato → entregar tal cual
                    return FileResponse(
                        path       = ruta_original,
                        filename   = file,
                        media_type = "application/pdf"
                    )

        raise HTTPException(status_code=404, detail="Archivo físico no encontrado.")
    finally:
        db.close()




@app.get("/descargar-lote")
def descargar_lote(ids: str = Query(...)):
    """
    Recibe una lista de IDs separados por coma: ?ids=1,2,3
    Devuelve un ZIP con todos los archivos (convertidos a PDF si son .docx)
    """
    db: Session = SessionLocal()
    try:
        lista_ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
        if not lista_ids:
            raise HTTPException(status_code=400, detail="IDs inválidos.")

        candidatos = db.query(Candidato).filter(Candidato.id.in_(lista_ids)).all()
        if not candidatos:
            raise HTTPException(status_code=404, detail="No se encontraron candidatos.")

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for c in candidatos:
                archivo_encontrado = None
                for root, dirs, files in os.walk("descargas"):
                    for file in files:
                        if file == c.nombre_archivo:
                            archivo_encontrado = os.path.join(root, file)
                            break

                if not archivo_encontrado:
                    continue

                ext = os.path.splitext(archivo_encontrado)[1].lower()

                if ext in (".docx", ".doc"):
                    # Convertir a PDF
                    nombre_pdf = os.path.splitext(c.nombre_archivo)[0] + ".pdf"
                    ruta_pdf   = os.path.join(tempfile.gettempdir(), nombre_pdf)
                    try:
                        convert(archivo_encontrado, ruta_pdf)
                        zf.write(ruta_pdf, nombre_pdf)
                    except Exception:
                        # Si falla la conversión, incluir el Word original
                        zf.write(archivo_encontrado, c.nombre_archivo)
                else:
                    zf.write(archivo_encontrado, c.nombre_archivo)

        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=hojas_de_vida.zip"}
        )
    finally:
        db.close()