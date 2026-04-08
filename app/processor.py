import os
import re
import hashlib
import fitz
import json
import logging
import pytesseract
import pdfplumber
from pdf2image import convert_from_path
from docx import Document
from sentence_transformers import SentenceTransformer
from app.database import SessionLocal
from app.models import Candidato
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

logging.getLogger("pdfminer").setLevel(logging.ERROR)

pytesseract.pytesseract.tesseract_cmd = r"C:\Users\Jalza\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\Users\Jalza\AppData\Local\Programs\poppler-25.12.0\Library\bin"

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

CATEGORIAS_CV = {
    "perfil": "resumen profesional del candidato, objetivo laboral, descripción personal sobre sí mismo",
    "experiencia": "trabajos anteriores, empresas donde trabajó, cargos ocupados, funciones realizadas",
    "educacion": "títulos obtenidos, universidades, colegios, grados académicos, años de estudio",
    "habilidades": "competencias técnicas y blandas, conocimientos, herramientas, programas que maneja",
    "formacion_complementaria": "cursos, diplomados, certificaciones, talleres, capacitaciones adicionales",
}

_embeddings_categorias = None






# ============================================================
# PARCHE 1: Detector de texto sin espacios + corrector
# Agregar estas funciones ANTES de extraer_texto_pdf()
# ============================================================

def _detectar_texto_comprimido(texto: str) -> bool:
    """
    Detecta si el texto extraído tiene palabras pegadas (sin espacios).
    Criterio: ratio de chars/palabras muy alto (palabras muy largas en promedio).
    """
    palabras = texto.split()
    if len(palabras) < 20:
        return False
    promedio_largo = sum(len(p) for p in palabras) / len(palabras)
    # Si el promedio de chars por "palabra" supera 12, probablemente hay texto pegado
    return promedio_largo > 12


# Instalar wordsegment una sola vez: pip install wordsegment
# Si no está disponible, usar separación heurística por mayúsculas
def _separar_palabras_pegadas(texto: str) -> str:
    """
    Intenta separar palabras pegadas usando dos estrategias:
    1. wordsegment (si está instalado) — más preciso
    2. Heurística de mayúsculas — fallback rápido
    """
    try:
        import wordsegment
        wordsegment.load()

        lineas_resultado = []
        for linea in texto.split('\n'):
            palabras_linea = []
            for token in linea.split():
                # Solo segmentar tokens muy largos (>15 chars) sin guiones ni puntos
                if len(token) > 15 and not re.search(r'[-./\d]', token):
                    segmentado = ' '.join(wordsegment.segment(token.lower()))
                    # Preservar mayúscula inicial si el token original la tenía
                    if token[0].isupper():
                        segmentado = segmentado.capitalize()
                    palabras_linea.append(segmentado)
                else:
                    palabras_linea.append(token)
            lineas_resultado.append(' '.join(palabras_linea))
        return '\n'.join(lineas_resultado)

    except ImportError:
        # Fallback: insertar espacio antes de cada mayúscula que siga a minúscula
        # Ejemplo: "IngenieroIndustrial" → "Ingeniero Industrial"
        texto_sep = re.sub(r'([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])', r'\1 \2', texto)
        # También separar dígitos pegados a letras
        texto_sep = re.sub(r'([a-záéíóúñA-ZÁÉÍÓÚÑ])(\d)', r'\1 \2', texto_sep)
        texto_sep = re.sub(r'(\d)([a-záéíóúñA-ZÁÉÍÓÚÑ])', r'\1 \2', texto_sep)
        return texto_sep


def _separar_palabras_por_mayusculas(texto: str) -> str:
    """
    Separación heurística rápida sin dependencias externas.
    Separa: CamelCase, texto•punto, dígito+letra, etc.
    """
    # CamelCase: insertar espacio antes de mayúscula que sigue a minúscula
    texto = re.sub(r'([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])', r'\1 \2', texto)
    # Separar números pegados a letras
    texto = re.sub(r'([a-záéíóúñA-ZÁÉÍÓÚÑ])(\d{4})', r'\1 \2', texto)
    texto = re.sub(r'(\d{4})([a-záéíóúñA-ZÁÉÍÓÚÑ])', r'\1 \2', texto)
    # Separar bullet "•" pegado
    texto = re.sub(r'•', ' • ', texto)
    # Limpiar espacios múltiples
    texto = re.sub(r'[ \t]{2,}', ' ', texto)
    return texto

# ===============================
# UTILIDADES
# ===============================

def calcular_hash(ruta):
    with open(ruta, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def limpiar_texto(texto):
    texto = re.sub(r'[ \t]+', ' ', texto)
    texto = re.sub(r'\n+', '\n', texto)
    return texto.strip()

def get_embeddings_categorias():
    global _embeddings_categorias
    if _embeddings_categorias is None:
        _embeddings_categorias = {
            cat: embedding_model.encode(desc)
            for cat, desc in CATEGORIAS_CV.items()
        }
    return _embeddings_categorias


def clasificar_bloque(texto: str) -> str:
    if len(texto.strip()) < 20:
        return "desconocido"
    emb_bloque = embedding_model.encode(texto[:500])
    emb_cats = get_embeddings_categorias()
    scores = {
        cat: cosine_similarity([emb_bloque], [emb_cat])[0][0]
        for cat, emb_cat in emb_cats.items()
    }
    mejor = max(scores, key=scores.get)
    return mejor if scores[mejor] >= 0.25 else "desconocido"
# ===============================
# PALABRAS CLAVE PARA DETECTAR ANEXOS
# ===============================

PALABRAS_FIN_CV = [
    "referencias personales",
    "referencias laborales",
    "referencias profesionales",
    "\nreferencias\n",
    "jefe inmediato:",
    "república de colombia",
    "ministerio de educación nacional",
    "confiere el título",
    "acta de grado",
    "certificado de aprobación",
    "certificado de asistencia",
    "a quien pueda interesar",
    "dado en la ciudad de",
    "coursera",
    "en cumplimiento de la ley 119",
    "servicio nacional de aprendizaje sena",
    "para todos los efectos legales",
    "pueden ser verificadas",
    "resolucion no.",
    "resolución no.",
    "artículo primero",
    "articulo primero",
    "notifíquese y cúmplase",
    "notifiquese y cumplase",
    "el comité de escalafón",
    "el comite de escalafon",
    "inscripcion en el escalafon",
    "inscripción en el escalafón",
    "página 1 de",
    "pagina 1 de",
    "secretario de despacho",
    "director administrativo de talento humano",
# Indicadores de cartas laborales y certificados oficiales

]

TITULOS_SECCION_CV = [
    "\nexperiencia\n",  # ← AÑADIR
    "\nexperiencia laboral\n",
    "\nexperiencia profesional\n",
    "\nperfil laboral\n",
    "\nperfil profesional\n",
    "\nhabilidades\n",
    "\neducación\n",
    "\neducacion\n",
    "\nwork experience\n",
    "\nexperience\n",
    "\neducation\n",
    "\nskills\n",
    "\nprofile\n",
    "\nsummary\n",
]

# Añadir junto a los otros patrones globales
PATRON_NIT = re.compile(r'\bNIT\s*[:\-]?\s*\d[\d\.\-]+', re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────────
# MEJORA #1 — Patrón de fechas laborales para detectar páginas de continuación
# ─────────────────────────────────────────────────────────────────────────────
PATRON_FECHA_LABORAL = re.compile(
    r'\b(20\d{2}|19\d{2})\s*[-–]\s*(20\d{2}|presente|actual|current|hoy)\b',
    re.IGNORECASE
)

def es_pagina_anexo(texto, texto_previo: str = ""):
    if not texto or len(texto.strip()) < 20:
        return False

    texto_lower = "\n" + texto.lower().strip() + "\n"

    for titulo in TITULOS_SECCION_CV:
        if titulo in texto_lower:
            return False

    coincidencias = sum(1 for p in PALABRAS_FIN_CV if p in texto_lower)

    # Carta laboral con NIT explícito → es anexo con umbral mínimo
    if bool(PATRON_NIT.search(texto)) and coincidencias >= 1:
        return True

    # ← NUEVO: Página de referencias → es anexo con 1 sola coincidencia
    REFERENCIAS_KEYWORDS = [
        "\nreferencias familiares\n", "\nreferencias personales\n",
        "\nreferencias laborales\n", "\nreferencias profesionales\n",
    ]
    if any(k in texto_lower for k in REFERENCIAS_KEYWORDS):
        return True

    if PATRON_FECHA_LABORAL.search(texto) and len(texto_previo.strip()) > 200:
        return coincidencias >= 3

    return coincidencias >= 2


# ===============================
# DETECCIÓN TEXTO ESPACIADO
# ===============================

def tiene_texto_espaciado(texto):
    patron = re.compile(r'(?:[A-ZÁÉÍÓÚÑ] ){4,}[A-ZÁÉÍÓÚÑ]')
    return bool(patron.search(texto))

# ===============================
# EXTRACCIÓN POR PÁGINA CON COLUMNAS
# ===============================

def extraer_pagina_columnas_fitz(pagina):
    bloques = pagina.get_text("blocks")
    bloques = [b for b in bloques if b[6] == 0 and b[4].strip()]

    if not bloques:
        return ""

    ancho = pagina.rect.width
    xs = [(b[0] + b[2]) / 2 for b in bloques]
    izquierda = sum(1 for x in xs if x < ancho * 0.45)
    derecha   = sum(1 for x in xs if x > ancho * 0.55)
    dos_columnas = izquierda > 2 and derecha > 2

    if not dos_columnas:
        bloques.sort(key=lambda b: b[1])
        return "\n".join(b[4].strip() for b in bloques)

    bloques.sort(key=lambda b: (round(b[1] / 8) * 8, b[0]))
    texto = []
    for b in bloques:
        linea = b[4].strip()
        if linea:
            texto.append(linea)
    return "\n".join(texto)


# ===============================
# EXTRACCIÓN CON PDFPLUMBER
# ===============================

def reconstruir_lineas(words, tolerancia=4):
    if not words:
        return ""
    lineas = {}
    for w in words:
        top_key = round(w['top'] / tolerancia) * tolerancia
        if top_key not in lineas:
            lineas[top_key] = []
        lineas[top_key].append(w)
    resultado = []
    for top_key in sorted(lineas.keys()):
        palabras = sorted(lineas[top_key], key=lambda w: w['x0'])
        resultado.append(" ".join(w['text'] for w in palabras))
    return "\n".join(resultado)


TITULOS_SIDEBAR = [
    "habilidades", "habilidades técnicas", "habilidades blandas",
    "competencias", "skills", "soft skills", "hard skills",
    "idiomas", "languages", "language",
    "referencias", "references",
    "contacto", "contact", "datos personales",
    "formación complementaria", "formacion complementaria",
    "certificaciones", "certifications",
    "herramientas", "tools",
]


def _es_columna_sidebar(texto: str) -> bool:
    texto_lower = texto.lower()
    titulos_principales = [
        "experience", "experiencia", "education", "educacion", "educación",
        "work experience", "experiencia laboral", "experiencia profesional",
        "perfil", "profile", "summary",
    ]
    for t in titulos_principales:
        if t in texto_lower:
            return False
    hits = sum(1 for t in TITULOS_SIDEBAR if t in texto_lower)
    if hits >= 1:
        return True
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    if len(lineas) >= 3:
        cortas = sum(1 for l in lineas if len(l) <= 40)
        ratio_cortas = cortas / len(lineas)
        promedio_chars = sum(len(l) for l in lineas) / len(lineas)
        if ratio_cortas > 0.80 and promedio_chars < 30:
            return True
    return False


PATRON_INICIO_BULLET = re.compile(r'^[\•\-\–\*◆▪○●]\s*')
PATRON_INICIO_NUEVA_SECCION = re.compile(
    r'^(Cargo|Jefe|Inicio|Funciones|Dirección|Empresa|JEFE|CARGO|INICIO|FUNCIONES)',
    re.IGNORECASE
)

# ===============================
# SECCIONES CONOCIDAS (español + inglés)
# ===============================

SECCIONES_CONOCIDAS = [
    # ── Experiencia ──
    "experiencia laboral", "experiencia profesional", "experiencia", "experiencias de trabajo","experiencia laboral sector empresarial",
    "work experience", "professional experience", "experience",
    "employment history", "career history", "work history",
    "relevant experience", "internship", "practicas", "prácticas",
    # ── Educación ──
    "educacion", "educación", "formacion academica", "formación académica",
    "datos academicos","datos académicos","nivel educativo", "estudios", "formación", "formacion",
    "historial académico", "historial academico","datos académicos","estudios tecnicos","estudios técnicos",
    "información académica", "informacion academica","Estudios realizados",
    "experiencia académica", "experiencia academica",
    "education", "academic background", "academic history",
    "qualifications", "academic qualifications", "degrees",
    "training", "academic training", "academic experience",
    # ── Habilidades ──
    "habilidades", "mis habilidades", "habilidades técnicas", "habilidades blandas","conocimiento y habilidades en programas",
    "competencias", "aptitudes", "conocimientos", "fortalezas", "destrezas", "capacidades tecnicas","habilidades especializadas",
    "aptitudes y competencias",
    "skills", "core skills", "key skills", "technical skills",
    "soft skills", "hard skills", "competencies", "abilities",
    "areas of expertise", "expertise", "strengths",
    # ── Perfil / Resumen ──
    "perfil laboral", "perfil profesional", "perfil",
    "objetivo profesional","perfil ocupacional", "sobre mi", "sobre mí",
    "profile", "professional profile", "professional summary",
    "summary", "career summary", "career objective",
    "objective", "about me", "personal statement",
    "executive summary",
    # ── Formación complementaria ──
    "formación complementaria", "formacion complementaria",
    "educación informal", "educacion informal", "talleres y cursos", "cursos y certificaciones",
    "cursos", "certificaciones", "certificados", "capacitaciones", "diplomados",
    "courses", "certifications", "certificates",
    "professional development", "continuing education",
    "additional training", "training & certifications",
    "training and certifications", "otros estudios",
    # ── Idiomas ──
    "idiomas", "language", "languages", "language skills",
    # ── Otros ──
    "referencias", "referencias laborales", "referencias personales",
    "referencia familiar", "referencia familiar y personal",
    "references", "professional references",
    "logros", "achievements", "accomplishments",
    "proyectos", "projects", "key projects",
    "voluntariado", "volunteer", "volunteer experience",
    "datos personales", "informacion personal", "información personal",
    "personal information", "personal details", "contact information",
    "contactos", "contacto", "contact",
    "publicaciones", "publications",
    "premios", "awards", "honors",
    "intereses", "interests", "hobbies",
    "programas", "disponibilidad", "ubicación", "ubicacion",
    "desempeños", "desempenos", "logros y reconocimientos", "reconocimientos",
    "nota",
    # ── Espaciados OCR ──
    "h a b i l i d a d e s",
    "e d u c a c i ó n",
    "e x p e r i e n c i a",

    "idioma extranjero",
    "idiomas",
    "referencias familiares",
    "referencias personales",
    "referencias laborales",
]


def unir_lineas_partidas(texto: str) -> str:
    lineas = texto.split('\n')
    resultado = []
    i = 0
    while i < len(lineas):
        linea_actual = lineas[i]
        linea_stripped = linea_actual.strip()

        if not linea_stripped:
            resultado.append(linea_actual)
            i += 1
            continue

        # ← NUEVO: si la línea actual ES un título de sección → no intentar unir
        linea_lower = linea_stripped.lower()
        es_titulo_seccion = any(
            linea_lower == s.strip().lower() or linea_lower.startswith(s.strip().lower())
            for s in SECCIONES_CONOCIDAS
        )
        if es_titulo_seccion:
            resultado.append(linea_actual)
            i += 1
            continue

        while i + 1 < len(lineas):
            siguiente = lineas[i + 1].strip()
            if not siguiente:
                break

            empieza_minuscula  = siguiente[0].islower()
            empieza_conjuncion = bool(re.match(
                r'^(y |e |o |u |a |al |de |del |en |con |que |por |sin |los |las |un |una )',
                siguiente, re.IGNORECASE
            ))
            no_tiene_bullet  = not PATRON_INICIO_BULLET.match(siguiente)
            no_es_campo      = not re.match(r'^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s*:', siguiente)
            no_es_seccion    = not PATRON_INICIO_NUEVA_SECCION.match(siguiente)
            linea_incompleta = (
                not linea_stripped.endswith('.')
                and not linea_stripped.endswith(':')
                and len(linea_stripped) > 15
            )

            if (empieza_minuscula or empieza_conjuncion) \
                    and no_tiene_bullet and no_es_campo \
                    and no_es_seccion and linea_incompleta:
                linea_actual   = linea_actual.rstrip() + ' ' + siguiente
                linea_stripped = linea_actual.strip()
                i += 1
            else:
                break

        resultado.append(linea_actual)
        i += 1

    return '\n'.join(resultado)


def extraer_pagina_pdfplumber(pagina, es_primera_pagina: bool = True):
    import re
    words = pagina.extract_words()
    if not words:
        return ""

    ancho = pagina.width
    bins = 20
    bin_size = ancho / bins
    conteo = [0] * bins
    for w in words:
        cx = (w['x0'] + w['x1']) / 2
        idx = min(int(cx / bin_size), bins - 1)
        conteo[idx] += 1

    zona_inicio = int(bins * 0.25)
    zona_fin = int(bins * 0.75)
    zona = conteo[zona_inicio:zona_fin]
    min_d = min(zona)
    max_d = max(conteo)

    words_izq = [w for w in words if w['x0'] < ancho * 0.40]
    words_der = [w for w in words if w['x0'] >= ancho * 0.40]
    if len(words_izq) < 5 and len(words_der) >= 5:
        return reconstruir_lineas(words_der)
    if len(words_der) < 5 and len(words_izq) >= 5:
        return reconstruir_lineas(words_izq)

    if max_d == 0 or (min_d / max_d) > 0.4:
        return reconstruir_lineas(words)

    idx_min = zona.index(min_d) + zona_inicio
    corte_x = (idx_min + 0.5) * bin_size

    izq = [w for w in words if w['x0'] < corte_x]
    der = [w for w in words if w['x0'] >= corte_x]

    words_margen = [w for w in izq if w['x0'] < ancho * 0.12]
    if len(words_margen) / max(len(izq), 1) > 0.7:
        return reconstruir_lineas(words)

    if len(izq) < 5 or len(der) < 5:
        return reconstruir_lineas(words)

    texto_izq = reconstruir_lineas(izq)
    texto_der = reconstruir_lineas(der)

    titulos_principales = [
        "experience", "experiencia", "education", "educacion", "educación",
        "work experience", "experiencia laboral", "formación", "formacion",
        "habilidades", "perfil",
    ]
    score_der = sum(1 for t in titulos_principales if t in texto_der.lower())
    score_izq = sum(1 for t in titulos_principales if t in texto_izq.lower())

    def _ratio_texto_pegado(t: str) -> float:
        palabras = [p for p in t.split() if p.strip()]
        if len(palabras) < 5:
            return 0.0
        return sum(len(p) for p in palabras) / len(palabras)

    pegado_izq = _ratio_texto_pegado(texto_izq) > 10
    pegado_der = _ratio_texto_pegado(texto_der) > 10

    if pegado_izq and not pegado_der:
        return texto_der
    if pegado_der and not pegado_izq:
        return texto_izq

    if score_der == 0 and score_izq == 0:
        if not es_primera_pagina:
            if _es_columna_sidebar(texto_izq):
                return texto_der
        return texto_izq + "\n" + texto_der

    if score_izq >= score_der:
        return texto_izq + "\n" + texto_der

    # score_der > score_izq → cuerpo principal está a la derecha
    # ── NUEVO: rescatar párrafo de perfil de la columna derecha ──
    # Algunos CVs de Canva/plantilla ponen: Nombre → párrafo perfil →
    # EXPERIENCIA LABORAL, todo en la columna derecha.
    TITULOS_EXPERIENCIA_CORTE = [
        "experiencia laboral", "experiencia profesional", "experiencia",
        "work experience", "employment history", "career history",
    ]
    der_lower = texto_der.lower()
    corte_exp_der = len(texto_der)
    for titulo in TITULOS_EXPERIENCIA_CORTE:
        m = re.search(
            r'(?:^|\n)[ \t]*' + re.escape(titulo) + r'[ \t]*(?:\n|:|\Z)',
            der_lower, re.IGNORECASE
        )
        if m and m.start() > 30:
            corte_exp_der = min(corte_exp_der, m.start())

    perfil_der = texto_der[:corte_exp_der].strip()

    # Intentar rescatar perfil del sidebar izquierdo si lo hay
    TITULOS_PERFIL_EN_SIDEBAR = [
        "sobre mí", "sobre mi", "perfil", "profile",
        "acerca de mí", "acerca de mi", "resumen", "summary",
        "objetivo", "objective", "about me",
    ]
    TITULOS_SIDEBAR_CORTE = [
        "habilidades", "skills", "idiomas", "languages", "contacto",
        "contact", "datos personales", "programas", "herramientas",
        "referencias", "disponibilidad", "ubicación", "ubicacion",
        "certifications", "certificaciones",
        "otros conocimientos",  # ← NUEVO
        "formación académica", "formacion academica",  # ← NUEVO
    ]

    izq_lower = texto_izq.lower()

    perfil_desde_titulo = ""
    for titulo in TITULOS_PERFIL_EN_SIDEBAR:
        m = re.search(
            r'(?:^|\n)[ \t]*' + re.escape(titulo) + r'[ \t]*(?:\n|$)',
            izq_lower, re.IGNORECASE
        )
        if m:
            perfil_desde_titulo = texto_izq[m.end():].strip()
            break

    corte_sidebar = len(texto_izq)
    for titulo in TITULOS_SIDEBAR_CORTE:
        m = re.search(
            r'(?:^|\n)[ \t]*' + re.escape(titulo) + r'[ \t]*(?:\n|$)',
            izq_lower, re.IGNORECASE
        )
        if m and m.start() > 30:
            corte_sidebar = min(corte_sidebar, m.start())
    parte_superior_izq = texto_izq[:corte_sidebar].strip()

    # ── Decidir qué usar como perfil ──
    # Prioridad: perfil explícito en sidebar > parte superior sidebar > perfil columna derecha
    hab_sidebar = extraer_habilidades_sidebar_final(izq)

    if perfil_desde_titulo and len(perfil_desde_titulo) > 50:
        return perfil_desde_titulo + "\n" + texto_der + ("\n" + hab_sidebar if hab_sidebar else "")

    if len(parte_superior_izq) > 50:
        if perfil_der and len(perfil_der) > 60 and perfil_der.lower() not in parte_superior_izq.lower():
            return (parte_superior_izq + "\nPERFIL PROFESIONAL\n" + perfil_der
                    + "\n" + texto_der
                    + ("\n" + hab_sidebar if hab_sidebar else ""))
        return parte_superior_izq + "\n" + texto_der + ("\n" + hab_sidebar if hab_sidebar else "")

    if perfil_der and len(perfil_der) > 60:
        return ("PERFIL PROFESIONAL\n" + perfil_der
                + "\n" + texto_der
                + ("\n" + hab_sidebar if hab_sidebar else ""))

    # ← NUEVO: si no hay perfil claro, igual rescatar habilidades del sidebar
    return texto_der + ("\n" + hab_sidebar if hab_sidebar else "")

def extraer_texto_pdf_pdfplumber(ruta):
    try:
        texto_paginas  = []
        texto_acumulado = ""

        with pdfplumber.open(ruta) as pdf:
            for i, pagina in enumerate(pdf.pages):
                contenido = extraer_pagina_pdfplumber(pagina, es_primera_pagina=(i == 0))

                # Página 1: siempre incluir
                if i == 0:
                    contenido = unir_lineas_partidas(contenido)   # ← NUEVO
                    texto_paginas.append(contenido)
                    texto_acumulado += "\n" + contenido
                    continue

                # NUEVO: página de imagen pura → saltar silenciosamente
                if len(contenido.strip()) < 20:
                    continue

                contenido_lower = "\n" + contenido.lower() + "\n"

                # Regla 1: tiene título de sección CV → incluir sin dudar
                if any(t in contenido_lower for t in TITULOS_SECCION_CV):
                    contenido = unir_lineas_partidas(contenido)   # ← NUEVO
                    texto_paginas.append(contenido)
                    texto_acumulado += "\n" + contenido
                    continue

                # Regla 2: tiene fechas laborales + texto previo → continuación
                if PATRON_FECHA_LABORAL.search(contenido) and len(texto_acumulado.strip()) > 200:
                    # NUEVO: verificar que no sea carta/certificado a pesar de tener fecha
                    if not es_pagina_anexo(contenido, texto_previo=texto_acumulado):
                        contenido = unir_lineas_partidas(contenido)   # ← NUEVO
                        texto_paginas.append(contenido)
                        texto_acumulado += "\n" + contenido
                        continue

                # Regla 3: es claramente un anexo → cortar
                if es_pagina_anexo(contenido, texto_previo=texto_acumulado):
                    break

                # Regla 4: duda → incluir
                contenido = unir_lineas_partidas(contenido)   # ← NUEVO
                texto_paginas.append(contenido)
                texto_acumulado += "\n" + contenido

        return "\n\n".join(texto_paginas)
    except Exception as e:
        logging.error(f"Error en extraer_texto_pdf_pdfplumber: {e}")
        return ""


# ===============================
# EXTRACCIÓN PDF PRINCIPAL
# ===============================

def extraer_texto_pdf(ruta):
    texto = extraer_texto_pdf_pdfplumber(ruta)

    # Fallback 1: fitz
    if len(texto.strip()) < 50:
        texto_paginas = []
        texto_acumulado = ""
        try:
            doc = fitz.open(ruta)
            for i, pagina in enumerate(doc):
                contenido = extraer_pagina_columnas_fitz(pagina)
                if i == 0:
                    texto_paginas.append(contenido)
                    texto_acumulado += "\n" + contenido
                    continue
                contenido_lower = "\n" + contenido.lower() + "\n"
                tiene_seccion = any(t in contenido_lower for t in TITULOS_SECCION_CV)
                tiene_fechas  = bool(PATRON_FECHA_LABORAL.search(contenido))
                if tiene_seccion or (tiene_fechas and len(texto_acumulado.strip()) > 200):
                    texto_paginas.append(contenido)
                    texto_acumulado += "\n" + contenido
                elif es_pagina_anexo(contenido, texto_previo=texto_acumulado):
                    break
                else:
                    texto_paginas.append(contenido)
                    texto_acumulado += "\n" + contenido
            doc.close()
        except Exception:
            pass
        texto = "\n\n".join(texto_paginas)

    # Fallback 2: OCR
    if len(texto.strip()) < 50:
        try:
            imagenes = convert_from_path(ruta, poppler_path=POPPLER_PATH)
            texto = ""
            for img in imagenes:
                texto += pytesseract.image_to_string(img, lang="spa+eng")
        except Exception:
            pass

    texto = limpiar_texto(texto)
    texto = normalizar_texto_duplicado(texto)
    texto = deduplicar_texto_spe(texto)

    # ← NUEVO PARCHE: corregir texto comprimido sin espacios
    if _detectar_texto_comprimido(texto):
        logging.info(f"Texto comprimido detectado en {ruta}, aplicando separación de palabras...")
        texto = _separar_palabras_por_mayusculas(texto)
        texto = limpiar_texto(texto)  # re-limpiar después de separar

    return texto

def extraer_texto_docx(ruta):
    doc = Document(ruta)
    texto = "\n".join([p.text for p in doc.paragraphs])
    return limpiar_texto(texto)

# ===============================
# DETECCIÓN FORMATO ESTÁNDAR
# ===============================

def es_formato_estandar(texto):
    return (
        "PERFIL LABORAL" in texto and
        "EXPERIENCIA LABORAL" in texto and
        "NIVEL EDUCATIVO" in texto
    )



SECCIONES_DATOS_PERSONALES = [
    "contactos", "contacto",
    "datos personales", "datos personal es",
    "informacion personal", "información personal",
    "personal information", "personal details", "contact information",
    "referencias", "referencias familiares", "referencias personales",
    "referencias laborales", "referencia familiar",
    "references", "professional references",
    "desempeños", "desempenos", "proyectos destacados",
    "proyectos", "projects", "key projects",
    "language", "languages",
]

# ===============================
# PATRONES DE RUIDO
# ===============================

PATRONES_RUIDO = [
    r"del caf[eé][\.\s]",
    r"^\s*con formaci[oó]n integral",
    r"república de colombia",
    r"servicio nacional de aprendizaje",
    r"en cumplimiento de la ley",
    r"firmado digitalmente",
    r"autenticidad del documento",
    r"scanned with",
    r"camscanner",
    r"el presente t[íi]tulo",
    r"fecha de nacim",
    r"lugar de nacimiento",
    r"hace constar que",
    r"se firma (el presente|para la presente|la presente)",
    r"en testimonio de lo anterior",
    r"cursó y aprobó",
    r"curso y aprobo",
    r"acuerdo\s*n[úu]m",
    r"código snies",
    r"notif[íi]quese y c[úu]mplase",
    r"art[íi]culo (primero|segundo|tercero|cuarto)",
    r"resoluci[oó]n\s*no\.",
    r"p[áa]gina \d+ de \d+",
    r"secretario de despacho",
    r"director (operativo|administrativo) de",
    r"elabor[oó]:",
    r"revis[oó]:",
    r"\b3[0-9]{9}\b",
    r"@gmail\.com", r"@hotmail\.com", r"@yahoo\.com",
    r"@.*\.(com|co|edu|net)",
    r"(?i)^conjunto\s+",
    r"(?i)^apartamento\s+",
    r"(?i)^carrera\s+\d+",
    r"(?i)^calle\s+\d+",
    r"(?i)^mz\s*\d+",
    r"(?i)^tel[:\s]",
    r"(?i)^cel[:\s]",
    r"(?i)^e-mail[:\s]",
    r"(?i)^correo[:\s]",
    r"(?i)^direcci[oó]n[:\s]",
    r"(?i)^tel[eé]fono[:\s]",
    r"(?i)^\s*nombre\s*$",
    r"(?i)^\s*documento\s+de\s*$",
    r"(?i)^\s*documento\s+de\s+identidad\s*$",
    r"(?i)^\s*fecha\s+de\s+nacimiento\s*$",
    r"(?i)^\s*lugar\s+de\s+nacimiento\s*$",
    r"(?i)^\s*estado\s+civil\s*$",
    r"(?i)^\s*ciudad\s*$",
    r"(?i)^\s*e-mail\s*$",
    r"(?i)^\s*tel[eé]fono\s*$",
    r"(?i)^\s*identidad\s*$",
    r"^[A-Za-záéíóúñ] [a-záéíóúñ] [a-záéíóúñ]",   # texto con espacios entre cada letra (burbujas)
]


SECCIONES_CORTE_PERFIL_EXTRA = [
    "conocimientos y habilidades en programas",
    "conocimiento y habilidades en programas",
    "conocimientos y habilidades",
    "habilidades técnicas",
    "habilidades tecnicas",
    "programas y herramientas",
    "manejo de software",
    "manejo de programas",
    "competencias técnicas",
    "competencias tecnicas",
    "datos personal es",      # OCR con espacio raro
]

def normalizar_texto_duplicado(texto: str) -> str:
    """Corrige texto donde cada letra aparece duplicada: DDAATTOOSS → DATOS"""
    lineas = texto.split('\n')
    resultado = []
    for linea in lineas:
        # Detectar si la línea tiene patrón de duplicación (cada char repetido)
        s = linea.strip()
        if len(s) >= 4:
            # Verificar si todos los chars están duplicados
            pares_ok = all(s[i] == s[i+1] for i in range(0, len(s)-1, 2) if s[i] != ' ')
            if pares_ok and len(s) % 2 == 0 and not re.search(r'\d', s):
                # Desduplicar: tomar uno de cada dos chars
                dedup = ''.join(s[i] for i in range(0, len(s), 2))
                resultado.append(dedup)
                continue
        resultado.append(linea)
    return '\n'.join(resultado)

def limpiar_ruido_ocr(texto):
    lineas_limpias = []
    for linea in texto.split("\n"):
        s = linea.strip()
        if len(s) < 4:
            continue
        if sum(1 for c in s if c in "¡¿_[]{}|\\^~`#$%&") / len(s) > 0.15:
            continue
        if not any(re.search(p, s, re.IGNORECASE) for p in PATRONES_RUIDO):
            lineas_limpias.append(s)
    return "\n".join(lineas_limpias).strip()

def limpiar_datos_personales(texto):
    SECCIONES_DATOS_PERSONALES_LOCAL = [
        "contactos", "contacto",
        "datos personales", "datos personal es", "datos personal",
        "informacion personal", "información personal",
        "personal information", "personal details", "contact information",
        "referencias", "referencias familiares", "referencias personales",
        "referencias laborales", "referencia familiar",
        "references", "professional references",
        "desempeños", "desempenos", "proyectos destacados",
        "proyectos", "projects", "key projects",
        "language", "languages",
    ] + SECCIONES_CORTE_PERFIL_EXTRA

    texto_lower = texto.lower()
    primer_corte = len(texto)          # ← se inicializa aquí
    for seccion in SECCIONES_DATOS_PERSONALES_LOCAL:
        m = re.search(
            r'(?:^|\n)\s*' + re.escape(seccion) + r'\s*(?:[:\n]|\Z)',  # ← patrón correcto
            texto_lower, re.IGNORECASE
        )
        if m and m.start() > 0:
            primer_corte = min(primer_corte, m.start())   # ← busca el más temprano
    if primer_corte < len(texto):
        texto = texto[:primer_corte].strip()
    return limpiar_ruido_ocr(texto)

# ===============================
# FUNCIONES AUXILIARES
# ===============================

def extraer_bloque_estandar(texto, inicio, fin_list):
    texto_norm = re.sub(r'(?m)^>\s*', '', texto)
    texto_upper = texto_norm.upper()

    patron_inicio = re.compile(
        r'(?:^|\n)\s*' + re.escape(inicio.upper()) + r'\s*(?:\n|:|\Z)',
        re.MULTILINE
    )
    m_inicio = patron_inicio.search(texto_upper)
    if not m_inicio:
        return ""

    start = m_inicio.start()
    sub = texto_norm[start:]
    sub_upper = sub.upper()
    fin = len(sub)

    for f in fin_list:
        patron_fin = re.compile(
            r'(?:^|\n)\s*' + re.escape(f.upper()) + r'\s*(?:\n|:|\Z)',
            re.MULTILINE
        )
        m = patron_fin.search(sub_upper)
        if m and m.start() > 5:
            fin = min(fin, m.start())

    return sub[:fin].strip()

def extraer_seccion_flexible(texto, palabras_clave):
    for palabra in palabras_clave:
        patron = re.compile(
            r'(?:^|\n)[ \t]*' + re.escape(palabra) + r'[ \t]*(?:\n|:)',
            re.IGNORECASE | re.MULTILINE
        )
        match = patron.search(texto)
        if not match:
            patron = re.compile(
                r'(?:^|\n)[ \t]*' + re.escape(palabra) + r'[ \t]*$',
                re.IGNORECASE | re.MULTILINE
            )
            match = patron.search(texto)
        if not match:
            continue

        sub = texto[match.start():]
        sub_lower = sub.lower()
        corte = len(sub)

        for seccion in SECCIONES_CONOCIDAS:
            if seccion in palabras_clave:
                continue
            m2 = re.search(
                r'\n[ \t]*' + re.escape(seccion) + r'[ \t]*(?:\n|:|\Z)',
                sub_lower, re.IGNORECASE
            )
            if m2 and m2.start() > 5:
                corte = min(corte, m2.start())

        bloque = limpiar_ruido_ocr(sub[:corte].strip())
        if len(bloque) > 10:
            return bloque
    return ""

# ===============================
# EXTRACCIÓN ESTÁNDAR (formato SPE)
# ===============================

def extraer_experiencia_estandar(texto):
    return extraer_bloque_estandar(texto, "EXPERIENCIA LABORAL",
        ["EDUCACIÓN", "NIVEL EDUCATIVO", "IDIOMAS", "REFERENCIAS", "HABILIDADES"])

def extraer_educacion_estandar(texto):
    return extraer_bloque_estandar(texto, "NIVEL EDUCATIVO",
        ["EDUCACIÓN INFORMAL", "IDIOMAS", "EXPERIENCIA LABORAL", "HABILIDADES"])

def _limpiar_bloque_habilidades(bloque: str) -> str:
    lineas = bloque.splitlines()
    limpias = []
    for linea in lineas:
        s = linea.strip()
        if not s:
            limpias.append(linea)
            continue
        s_lower = s.lower()
        es_fragmento = (
            (s[0].islower() and len(s) > 30) or
            re.match(r'^(y |e |con |de |en |así |me |a |al )', s_lower) or
            re.match(r'^/\s*(avanzado|intermedio|básico|alto|medio)', s_lower) or
            re.search(r'del caf[eé]|ciudadela|barrio\s+\w', s_lower)
        )
        if not es_fragmento:
            limpias.append(linea)
    return "\n".join(limpias).strip()

def extraer_habilidades_estandar(texto):
    for titulo in [
        "HABILIDADES", "COMPETENCIAS", "SKILLS",
        "IDIOMAS Y OTROS CONOCIMIENTOS",
        "IDIOMAS Y OTOS CONOCIMIENTOS",
    ]:
        bloque = extraer_bloque_estandar(texto, titulo,
            ["REFERENCIAS", "EDUCACIÓN", "NIVEL EDUCATIVO",
             "EXPERIENCIA LABORAL", "FORMACIÓN", "EDUCACIÓN INFORMAL"])
        if bloque and len(bloque.strip()) > 15:
            return _limpiar_bloque_habilidades(bloque)

    if "NIVEL EDUCATIVO" in texto.upper():
        bloque = extraer_bloque_estandar(texto, "IDIOMAS",
            ["REFERENCIAS", "EDUCACIÓN", "NIVEL EDUCATIVO",
             "EXPERIENCIA LABORAL", "FORMACIÓN"])
        if bloque and len(bloque.strip()) > 15:
            return _limpiar_bloque_habilidades(bloque)

    return ""

def extraer_formacion_complementaria_estandar(texto):
    return extraer_bloque_estandar(texto, "EDUCACIÓN INFORMAL",
        ["IDIOMAS", "IDIOMAS Y OTROS CONOCIMIENTOS", "IDIOMAS Y OTOS CONOCIMIENTOS",
         "REFERENCIAS", "HABILIDADES", "NIVEL EDUCATIVO"])

# ===============================
# EXTRACCIÓN MIXTA (español + inglés)
# ===============================

def extraer_experiencia_mixto(texto):
    experiencia = extraer_seccion_flexible(texto, [
        "experiencia laboral", "experiencia profesional", "experiencia","experiencia laboral sector empresarial",
        "prácticas", "practicas", "experiencias de trabajo","datos académicos",
        "work experience", "professional experience", "experience",
        "employment history", "career history", "work history",
        "relevant experience",
    ])

    # ← NUEVO: cortar antes de referencias si quedaron en el mismo bloque
    if experiencia:
        CORTES_REFS = [
            "referencias familiares", "referencias laborales",
            "referencias personales", "referencias profesionales",
            "\nreferencias\n",
        ]
        exp_lower = experiencia.lower()
        corte = len(experiencia)
        for ref in CORTES_REFS:
            m = re.search(r'\n[ \t]*' + re.escape(ref.strip()), exp_lower, re.IGNORECASE)
            if m and m.start() > 50:
                corte = min(corte, m.start())
        experiencia = experiencia[:corte].strip()

    cargos_huerfanos = _extraer_cargos_huerfanos(texto, experiencia or "")
    if cargos_huerfanos:
        experiencia = (experiencia or "") + "\n" + cargos_huerfanos
    return experiencia


def _extraer_cargos_huerfanos(texto: str, experiencia_ya_extraida: str) -> str:
    NO_ES_CARGO = [
        "ingeniería", "bootcamp", "bachiller", "diplomado", "certificado",
        "platzi", "coursera", "digital house", "digital hous", "senatic",
        "ibm", "ministerio tic", "universidad", "corporación", "institución",
        "back end en", "programación web", "principios de", "generative ai",
        "developing interpersonal", "funciones y", "algoritmos", "computacion",
        "lenguajes de programación", "iu training",
    ]
    ES_CARGO = [
        "desarrollador", "operador", "auxiliar", "programador", "ingeniero",
        "analista", "coordinador", "técnico", "director", "gerente",
        "asistente", "supervisor", "consultor", "jefe", "líder", "especialista",
        "developer", "engineer", "manager", "analyst",
    ]
    patron = re.compile(
        r'(?:^|\n)([^\n]{5,60})\n'
        r'([^\n]+\|\s*\d{4}[^\n]*)\n'
        r'((?:[^\n]+\n?){1,10})',
        re.MULTILINE
    )
    recuperados = []
    exp_lower = experiencia_ya_extraida.lower()
    for m in patron.finditer(texto):
        cargo = m.group(1).strip()
        cargo_lower = cargo.lower()
        if cargo_lower[:35] in exp_lower:
            continue
        if any(w in cargo_lower for w in NO_ES_CARGO):
            continue
        if not any(w in cargo_lower for w in ES_CARGO):
            continue
        recuperados.append(m.group(0).strip())
    return "\n\n".join(recuperados)

def extraer_educacion_mixto(texto):
    CORTES_EXTRA_EDUCACION = [
        "idioma extranjero", "idiomas", "language", "languages",
        "talleres y cursos", "talleres", "cursos",
        "referencias familiares", "referencias personales", "referencias",
        "experiencia laboral", "experiencia profesional","estudios tecnicos","estudios técnicos",
        "formación complementaria", "formacion complementaria",  # ← AÑADIR
        "habilidades", "habilidades técnicas","otros conocimientos",
        "otros conocimientos y habilidades",                   # ← AÑADIR
    ]
    bloque = extraer_seccion_flexible(texto, [
        "educacion", "educación", "formacion academica", "formación académica",
        "nivel educativo", "estudios","estudios realizados",
        "formación", "formacion","datos academicos","datos académicos",           # ← AÑADIR estas dos
        "información académica", "informacion academica",
        "experiencia académica", "experiencia academica",
        "education", "academic background", "academic history",
        "qualifications", "academic qualifications",
        "training", "academic training", "academic experience",
    ])
    if not bloque:
        return ""
    bloque_lower = bloque.lower()
    corte = len(bloque)
    for seccion in CORTES_EXTRA_EDUCACION:
        m = re.search(
            r'\n[ \t]*' + re.escape(seccion) + r'[ \t]*(?:\n|:|\Z)',
            bloque_lower, re.IGNORECASE
        )
        if m and m.start() > 10:
            corte = min(corte, m.start())
    return bloque[:corte].strip()

def _truncar_si_mezcla_experiencia(bloque: str) -> str:
    lineas = bloque.splitlines()
    for i, linea in enumerate(lineas):
        linea_s = linea.strip()
        linea_lower = linea_s.lower()
        if re.search(r'\|\s*20\d{2}', linea_s) or \
           re.search(r'\b20\d{2}\s*[-–]\s*(20\d{2}|presente)', linea_lower):
            corte = i
            while corte > 0 and not lineas[corte - 1].strip():
                corte -= 1
            if corte > 0:
                corte -= 1
            return "\n".join(lineas[:corte]).strip()
        cargos = [
            "desarrollador de software", "operador de medios",
            "auxiliar de", "programador ", "ingeniero ", "analista ",
            "coordinador ", "técnico ", "director ", "gerente ",
        ]
        if any(linea_lower.startswith(c) for c in cargos):
            if i > len(lineas) // 2:
                return "\n".join(lineas[:i]).strip()
    return bloque


def extraer_habilidades_mixto(texto):
    habilidades = extraer_seccion_flexible(texto, [
        "habilidades técnicas", "habilidades blandas", "capacidades tecnicas",
        "conocimiento y habilidades en programas",
        "conocimientos y habilidades en programas", "habilidades especializadas",
        "habilidades", "competencias", "aptitudes", "conocimientos","aptitudes y competencias",
        "mis habilidades", "destrezas",
        "skills", "core skills", "key skills", "technical skills",
        "soft skills", "hard skills", "competencies", "abilities",
        "areas of expertise", "expertise", "strengths",
    ])
    if habilidades:
        habilidades = _truncar_si_mezcla_experiencia(habilidades)
        habilidades = _limpiar_habilidades_espaciadas(habilidades)

    blandas = extraer_seccion_flexible(texto, [
        "habilidades blandas", "blandas", "soft skills", "competencias blandas",
    ])
    if blandas:
        blandas_lower = blandas.strip().lower()
        if blandas_lower not in (habilidades or "").lower():
            habilidades = (habilidades or "") + "\nHABILIDADES BLANDAS\n" + blandas

    fortalezas = extraer_seccion_flexible(texto, ["fortalezas", "strengths"])
    if fortalezas and fortalezas.strip().lower() not in (habilidades or "").lower():
        habilidades = (habilidades or "") + "\n" + fortalezas if habilidades else fortalezas



    return habilidades



def _limpiar_habilidades_espaciadas(bloque: str) -> str:
    """Elimina líneas que son texto con espacios entre letras (burbujas/chips de habilidades)"""
    lineas = bloque.splitlines()
    limpias = []
    for linea in lineas:
        s = linea.strip()
        if not s:
            limpias.append(linea)
            continue
        # Detectar texto espaciado: más del 30% de chars son espacios simples entre letras
        palabras = s.split()
        if len(palabras) >= 2:
            chars_letra = sum(len(p) for p in palabras)
            chars_total = len(s)
            # Si palabras muy cortas (1-3 chars) representan la mayoría → es texto espaciado de burbuja
            palabras_cortas = sum(1 for p in palabras if len(p) <= 3)
            if len(palabras) >= 4 and palabras_cortas / len(palabras) > 0.6:
                continue  # descartar línea
        limpias.append(linea)
    return "\n".join(limpias).strip()


# ── NUEVO: palabras técnicas cortas válidas (no son fragmentos de chips) ──
PALABRAS_TECNICAS_CORTAS_SIDEBAR = {
    'python', 'c/c++', 'c++', 'c#', 'iot', 'sql', 'php', 'css', 'xml',
    'aws', 'git', 'api', 'etl', 'html', 'java', 'ruby', 'rust',
    'kotlin', 'swift', 'bash', 'node', 'vue', 'react', 'flask', 'django',
    'matlab', 'latex', 'r',
}

def _es_fragmento_chip(txt: str) -> bool:
    """Detecta fragmentos de palabras partidas por chips/burbujas circulares."""
    txt_lower = txt.lower()
    if txt_lower in PALABRAS_TECNICAS_CORTAS_SIDEBAR:
        return False
    if txt.endswith('-'):          # "Comunica-", "Automatiza-"
        return True
    if txt[0].islower() and len(txt) <= 8:
        return True
    if re.match(r'^[a-záéíóúñ]{2,5}$', txt):
        return True
    if re.match(r'^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]$', txt):  # "Tr", "ón"
        return True
    return False


def extraer_habilidades_sidebar_final(words_izq: list) -> str:
    """
    Extrae habilidades directamente de los words de la columna izquierda,
    sin depender de reconstruir_lineas. Maneja dos casos:
    - Sidebar normal (listas de texto): reconstruye líneas limpiando texto colado
    - Sidebar con chips circulares (letras sueltas): extrae solo palabras completas
    """
    TITULOS_HAB = {'habilidades', 'skills', 'competencias', 'herramientas', 'programas', 'tools'}
    TITULOS_CORTE = {'idiomas', 'languages', 'contacto', 'contact', 'disponibilidad',
                     'ubicación', 'ubicacion', 'referencias', 'references', 'language'}
    STOP = {'de', 'en', 'el', 'la', 'los', 'las', 'un', 'una', 'y', 'o', 'a', 'al', 'del'}

    secciones_hab = {}
    secciones_corte = {}
    for w in words_izq:
        t = w['text'].strip().lower().rstrip(':')
        if t in TITULOS_HAB and t not in secciones_hab:
            secciones_hab[t] = w['top']
        if t in TITULOS_CORTE and t not in secciones_corte:
            secciones_corte[t] = w['top']

    if not secciones_hab:
        return ""

    top_inicio = min(secciones_hab.values())
    top_fin = float('inf')
    for top_corte in secciones_corte.values():
        if top_corte > top_inicio + 10:
            top_fin = min(top_fin, top_corte)
    if top_fin == float('inf'):
        top_fin = top_inicio + 500

    words_bloque = [w for w in words_izq if top_inicio <= w['top'] < top_fin]
    if not words_bloque:
        return ""

    total = len(words_bloque)
    letras_sueltas = sum(1 for w in words_bloque if len(w['text'].strip()) == 1)
    es_chips = total > 5 and (letras_sueltas / total) > 0.25

    if es_chips:
        palabras_utiles = []
        vistas = set()
        titulo_agregado = False
        for w in words_bloque:
            txt = w['text'].strip()
            txt_lower = txt.lower().rstrip(':')
            if len(txt) < 2:
                continue
            if txt_lower in TITULOS_HAB:
                if not titulo_agregado:
                    titulo_agregado = True
                    palabras_utiles.append('HABILIDADES')
                continue
            if txt_lower in STOP:
                continue
            if _es_fragmento_chip(txt):
                continue
            k = txt_lower
            if k not in vistas:
                vistas.add(k)
                palabras_utiles.append(txt)
        return "\n".join(palabras_utiles)
    else:
        lineas = reconstruir_lineas(words_bloque).splitlines()
        lineas_limpias = []
        for linea in lineas:
            linea_limpia = re.split(r' {3,}', linea)[0].strip()
            if linea_limpia:
                lineas_limpias.append(linea_limpia)
        return "\n".join(lineas_limpias)

def extraer_formacion_complementaria_mixto(texto):
    bloque = extraer_seccion_flexible(texto, [
        "talleres y cursos",              # ← MOVER AL PRIMERO
        "cursos y certificaciones",
        "educación informal", "educacion informal",
        "formación complementaria", "formacion complementaria",
        "cursos", "capacitaciones", "diplomados",
        "otros estudios", "estudios complementarios",
        "otros conocimientos",
        "courses", "certifications", "certificates",
        "professional development", "continuing education",
        "additional training", "training & certifications",
        "training and certifications",
    ])
    if not bloque:
        bloque = extraer_seccion_flexible(texto, ["formacion complementaria"])
    if not bloque:
        return ""
    lineas = bloque.splitlines()
    vistas = set()
    lineas_unicas = []
    for linea in lineas:
        key = re.sub(r'\s+', ' ', linea.strip().lower())
        if key and key not in vistas:
            vistas.add(key)
            lineas_unicas.append(linea)
    return "\n".join(lineas_unicas)

# ===============================
# NORMALIZAR HABILIDADES
# ===============================

def normalizar_habilidades(habilidades):
    if isinstance(habilidades, list):
        return ", ".join([str(h).strip() for h in habilidades if h])
    if not isinstance(habilidades, str):
        return ""
    texto = re.sub(r'^(HABILIDADES|SKILLS)\s*', '', habilidades.strip(), flags=re.IGNORECASE)
    if "\n" in texto:
        lineas = [l.strip(" •-·●○◆▪") for l in texto.split("\n") if len(l.strip()) > 2]
        return "\n".join(lineas)
    texto = re.sub(r'([a-záéíóúña-z])(\s+)([A-ZÁÉÍÓÚÑA-Z])', r'\1\n\3', texto)
    lineas = [l.strip(" •-·●○◆▪") for l in texto.split("\n") if len(l.strip()) > 2]
    return "\n".join(lineas)

# ===============================
# LIMPIAR MEZCLA DE COLUMNAS
# ===============================

def limpiar_columna_izquierda(texto):
    patrones = [
        r'(?i)formaci[oó]n\s+complementaria\b[^\n]*\n',
        r'(?i)diplomado\s+internacional[^\n]*\n',
        r'(?i)diplomado\s+en[^\n]*\n',
        r'(?i)community\s+management[^\n]*\n',
        r'(?i)duraci[oó]n\s*\d+\s*horas?[^\n]*\n',
        r'(?i)taller\s+de\s+reporterismo[^\n]*\n',
        r'(?i)experiencias\s+en\s+educaci[oó]n[^\n]*\n',
        r'(?i)\bii\b\s+coloquio[^\n]*\n',
        r'(?i)desempe[ñn]os?\b[^\n]*\n',
        r'\d+\s*y\s*\d+\s*de\s*\w+\s*de\s*\d{4}\n',
    ]
    for p in patrones:
        texto = re.sub(p, '\n', texto, flags=re.IGNORECASE)
    return texto


def deduplicar_texto_spe(texto):
    bloques = re.split(r'\n{2,}', texto.strip())
    vistos = []
    resultado = []
    for bloque in bloques:
        normalizado = re.sub(r'\s+', ' ', bloque.strip().lower())
        if not normalizado:
            continue
        es_duplicado = False
        for visto in vistos[-5:]:
            if normalizado == visto:
                es_duplicado = True
                break
            palabras_nuevo = set(normalizado.split())
            palabras_visto = set(visto.split())
            if len(palabras_nuevo) > 0 and len(palabras_visto) > 0:
                interseccion = len(palabras_nuevo & palabras_visto)
                solapamiento = interseccion / max(len(palabras_nuevo), len(palabras_visto))
                ratio_longitud = min(len(normalizado), len(visto)) / max(len(normalizado), len(visto))
                if solapamiento > 0.85 and ratio_longitud > 0.80:
                    es_duplicado = True
                    break
        if not es_duplicado:
            resultado.append(bloque.strip())
            vistos.append(normalizado)
    return "\n\n".join(resultado)

# ===============================
# DETECTOR DE PERFIL SIN TÍTULO — MEJORADO
# ===============================

# ─────────────────────────────────────────────────────────────────────────────
# MEJORA #2 — extraer_perfil_sin_titulo más robusto
#
# Problema anterior: perfiles sin encabezado que solo tienen frases cortas
# de presentación, adjetivos profesionales o sectores laborales quedaban
# vacíos porque la lista de "palabras_profesionales" era muy limitada.
#
# Solución:
#   - Lista PALABRAS_PERFIL_PROFESIONAL ampliada con: títulos abreviados
#     (Ing., Lic., Tec.), verbos de presentación (me desempeño, cuento con,
#     busco, aspiro), adjetivos de perfil (proactivo, responsable, creativo)
#     y sectores laborales (salud, ventas, logística, manufactura...).
#   - Límite de 800 chars para evitar que el bloque absorba todo el CV
#     cuando el corte de sección falla.
# ─────────────────────────────────────────────────────────────────────────────

PALABRAS_PERFIL_PROFESIONAL = [
    # Títulos / roles (español)
    "ingeniero", "ing.", "técnico", "tec.", "tecnólogo",
    "licenciado", "lic.", "profesional", "contador", "economista",
    "administrador", "abogado", "médico", "arquitecto", "docente",
    "maestro", "psicólogo", "comunicador", "diseñador", "programador",
    "desarrollador", "analista", "coordinador", "auxiliar", "operario",
    # Títulos / roles (inglés)
    "engineer", "developer", "manager", "analyst", "specialist",
    "consultant", "coordinator", "supervisor", "architect",
    # Verbos / frases de perfil (español)
    "me desempeño", "me encuentro", "cuento con", "busco", "aspiro",
    "me caracterizo", "poseo", "tengo experiencia", "soy profesional",
    "mi objetivo", "orientado", "comprometido", "apasionado",
    "enfocado", "interesado en", "dispuesto",
    # Verbos / frases de perfil (inglés)
    "i am", "i have", "i seek", "looking for", "motivated by",
    "passionate about", "experienced in", "skilled in",
    # Sustantivos profesionales (español)
    "experiencia", "conocimientos", "habilidad", "capacidad",
    "gestión", "diseño", "sistemas", "software", "automatización",
    "análisis", "liderazgo", "comunicación", "coordinación",
    "proyectos", "implementación", "desarrollo", "investigación",
    "innovación", "planificación", "electrónica", "instrumentación",
    # Sustantivos profesionales (inglés)
    "experience", "knowledge", "skills", "expertise", "leadership",
    "communication", "teamwork", "management", "research", "innovation",
    # Adjetivos de perfil (español)
    "proactivo", "responsable", "creativo", "dinámico", "organizado",
    "puntual", "honesto", "colaborativo", "autónomo", "adaptable",
    "empático", "resolutivo", "eficiente", "metódico",
    # Adjetivos de perfil (inglés)
    "proactive", "responsible", "creative", "dynamic", "organized",
    "punctual", "collaborative", "autonomous", "adaptable", "efficient",
    "dedicated", "motivated", "passionate", "results-driven",
    # Sectores laborales (español)
    "salud", "educación", "ventas", "logística", "manufactura",
    "construcción", "finanzas", "contabilidad", "marketing",
    "recursos humanos", "tecnología", "telecomunicaciones",
    "agroindustria", "minería", "transporte", "comercio",
    # Sectores laborales (inglés)
    "healthcare", "education", "sales", "logistics", "manufacturing",
    "construction", "finance", "accounting", "marketing",
    "human resources", "technology", "telecommunications",
]

def extraer_perfil_sin_titulo(texto):
    """
    Extrae el perfil cuando no tiene encabezado explícito.

    MEJORA: indicadores ampliados (títulos abreviados, verbos de presentación,
    adjetivos y sectores laborales) + límite de 800 chars para no absorber
    el CV completo cuando el corte de sección falla.
    """
    texto_norm = texto.strip()
    texto_lower = texto_norm.lower()

    secciones_corte = [
        # Español
        "experiencia laboral", "experiencia profesional", "experiencia académica",
        "experiencia academica", "experiencia",
        "educacion", "educación", "formacion", "formación",
        "habilidades", "competencias",
        "datos personales", "informacion personal", "información personal",
        "referencias", "referencias laborales",
        "idiomas", "cursos", "certificaciones",
        "programas", "disponibilidad", "ubicación", "ubicacion",
        # Inglés
        "work experience", "professional experience", "experience",
        "employment history", "career history",
        "education", "academic background", "qualifications",
        "skills", "core skills", "key skills", "technical skills",
        "competencies", "expertise", "strengths",
        "personal information", "personal details", "contact information",
        "references", "language", "languages", "certifications", "courses",
        "achievements", "projects",
    ]

    primer_corte = len(texto_norm)
    for sec in secciones_corte:
        patron = re.compile(
            r'(?:^|\n)\s*' + re.escape(sec) + r'\s*(?:\n|:|\Z)',
            re.IGNORECASE
        )
        m = patron.search(texto_lower)
        if m and m.start() > 20:
            primer_corte = min(primer_corte, m.start())

    bloque_inicial = texto_norm[:primer_corte].strip()

    if len(bloque_inicial) < 30:
        return ""

    bloque_limpio = limpiar_datos_personales(bloque_inicial)

    if len(bloque_limpio) < 20:
        return ""

        # ← NUEVO: limpiar nombre/cédula del inicio del perfil
    lineas = bloque_limpio.splitlines()
    lineas_perfil = []
    encontro_contenido = False
    for linea in lineas:
        s = linea.strip()
        # Saltar líneas que son solo nombre (todo mayúsculas, cortas) o cédula
        if not encontro_contenido:
            if re.match(r'^[A-ZÁÉÍÓÚÑ\s]{2,30}$', s) and len(s.split()) <= 3:
                continue  # línea de nombre en mayúsculas
            if re.match(r'^C\.?C\.?\s*[\d\.,]+', s, re.IGNORECASE):
                continue  # cédula
            if re.match(r'^\d{1,3}\s+años?$', s, re.IGNORECASE):
                continue  # edad suelta
        encontro_contenido = True
        lineas_perfil.append(linea)
    bloque_limpio = "\n".join(lineas_perfil).strip()

    # Verificar que el bloque tiene contenido profesional real
    bloque_lower = bloque_limpio.lower()
    tiene_contenido = any(p in bloque_lower for p in PALABRAS_PERFIL_PROFESIONAL)

    if not tiene_contenido:
        return ""

    # Limitar a 800 chars para no absorber todo el CV
    if len(bloque_limpio) > 800:
        m_punto = re.search(r'\.\s*\n', bloque_limpio[:800])
        if m_punto:
            bloque_limpio = bloque_limpio[:m_punto.end()].strip()
        else:
            idx_nl = bloque_limpio[:800].rfind('\n')
            bloque_limpio = bloque_limpio[:idx_nl].strip() if idx_nl > 100 else bloque_limpio[:800].strip()

    return bloque_limpio

def _validar_habilidades(habilidades: str, perfil: str, experiencia: str, educacion: str) -> str:

    if not habilidades:
        return ""

    # Tomar solo las primeras líneas no vacías y no duplicadas
    otras_secciones = " ".join([perfil or "", experiencia or "", educacion or ""])
    otras_norm = re.sub(r'\s+', ' ', otras_secciones.lower())

    lineas_limpias = []
    for linea in habilidades.split('\n'):
        s = linea.strip()
        if not s:
            continue
        s_norm = re.sub(r'\s+', ' ', s.lower())
        # Saltar línea si ya aparece casi igual en otras secciones
        if len(s_norm) > 15 and s_norm in otras_norm:
            continue
        lineas_limpias.append(s)

    resultado = '\n'.join(lineas_limpias).strip()

    # Si lo que queda es muy poco o muy largo (señal de mezcla), dejar vacío
    if len(resultado) > 1200:
        return ""

    return resultado

# ===============================
# ESTRUCTURADOR CENTRAL
# ===============================

def estructurar_cv(texto):
    if es_formato_estandar(texto):
        perfil                   = extraer_bloque_estandar(texto, "PERFIL LABORAL", ["EXPERIENCIA LABORAL"])
        experiencia              = extraer_experiencia_estandar(texto)
        educacion                = extraer_educacion_estandar(texto)
        habilidades              = extraer_habilidades_estandar(texto)
        formacion_complementaria = extraer_formacion_complementaria_estandar(texto)
    else:
        texto_limpio = limpiar_columna_izquierda(texto)

        perfil_raw = extraer_seccion_flexible(texto_limpio, [
            "perfil laboral","perfil ocupacional", "perfil profesional", "perfil",
            "objetivo profesional", "sobre mi", "sobre mí","perfil ocupacional",
            "profile", "professional profile", "professional summary",
            "summary", "career summary", "career objective",
            "objective", "about me", "personal statement",
            "executive summary",
        ])
        perfil = limpiar_datos_personales(perfil_raw) if perfil_raw else ""

        if not perfil:
            perfil = extraer_perfil_sin_titulo(texto_limpio)
            if perfil:
                perfil = unir_lineas_partidas(perfil)

        experiencia              = extraer_experiencia_mixto(texto_limpio)
        educacion                = extraer_educacion_mixto(texto_limpio)
        habilidades              = extraer_habilidades_mixto(texto_limpio)
        formacion_complementaria = extraer_formacion_complementaria_mixto(texto_limpio)

        if not experiencia:
            experiencia = extraer_seccion_flexible(texto_limpio, [
                "experiencia laboral", "experiencia profesional", "experiencia",
                "work experience", "professional experience", "experience",
                "employment history",
            ])
        if not educacion:
            educacion = extraer_educacion_mixto(texto_limpio)
        if not habilidades:
            habilidades = extraer_seccion_flexible(texto_limpio, [
                "habilidades", "competencias", "aptitudes", "conocimientos", "destrezas",
                "skills", "core skills", "technical skills", "competencies",
            ])
        if not formacion_complementaria:
            formacion_complementaria = extraer_seccion_flexible(texto_limpio, [
                "educación informal", "educacion informal",
                "formación complementaria", "formacion complementaria",
                "cursos", "certificaciones", "diplomados",
                "courses", "certifications", "professional development",
                "additional training",
            ])

        # Evitar que el perfil contenga el inicio de la experiencia
        if perfil and experiencia:
            exp_inicio = experiencia[:80].strip().lower()
            if exp_inicio and exp_inicio in perfil.lower():
                idx = perfil.lower().find(exp_inicio)
                if idx > 0:
                    perfil = limpiar_ruido_ocr(perfil[:idx].strip())

    # Limpiar perfil duplicado
    if perfil:
        mitad = len(perfil) // 2
        primera = re.sub(r'\s+', ' ', perfil[:mitad].strip().lower())
        segunda  = re.sub(r'\s+', ' ', perfil[mitad:].strip().lower())
        palabras_1 = set(primera.split())
        palabras_2 = set(segunda.split())
        if palabras_1 and palabras_2:
            overlap = len(palabras_1 & palabras_2) / max(len(palabras_1), len(palabras_2))
            if overlap > 0.70:
                perfil = perfil[:mitad].strip()

    if habilidades:
        habilidades = _validar_habilidades(habilidades, perfil, experiencia, educacion)

    return {
        "perfil":                   perfil.strip()                   if perfil                   else "",
        "experiencia":              experiencia.strip()              if experiencia              else "",
        "educacion":                educacion.strip()                if educacion                else "",
        "habilidades":              normalizar_habilidades(habilidades),
        "formacion_complementaria": formacion_complementaria.strip() if formacion_complementaria else "",
    }



def estructurar_cv_inteligente(texto: str) -> dict:

    datos = estructurar_cv(texto)

    secciones_criticas = ["experiencia", "educacion", "habilidades"]
    vacias = [s for s in secciones_criticas if not datos.get(s)]

    if not vacias:
        return datos  # todo bien, salir rápido

    # Paso 2: clasificador semántico con embeddings locales
    logging.info(f"Secciones vacías: {vacias}. Intentando con embeddings...")
    for bloque in re.split(r'\n{2,}', texto.strip()):
        if len(bloque.strip()) < 30:
            continue
        categoria = clasificar_bloque(bloque)
        if categoria in vacias and not datos.get(categoria):
            datos[categoria] = bloque.strip()
            vacias = [s for s in vacias if not datos.get(s)]
            if not vacias:
                break

    if vacias:
        logging.info(f"Secciones que no se pudieron detectar: {vacias}")

    return datos

# ===============================
# PROCESAMIENTO PRINCIPAL
# ===============================

hashes_procesados = set()

def procesar_archivos():
    db = SessionLocal()
    BASE_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    carpeta = os.path.join(BASE_PROJECT_DIR, "descargas")

    if not os.path.exists(carpeta):
        db.close()
        return {"insertados": 0, "omitidos": 0, "total_en_db": 0}

    insertados = 0
    omitidos   = 0
    candidatos_temp   = []
    textos_embeddings = []

    for root, dirs, files in os.walk(carpeta):
        for file in files:
            if not file.lower().endswith((".pdf", ".docx")):
                continue

            ruta         = os.path.join(root, file)
            hash_archivo = calcular_hash(ruta)

            if hash_archivo in hashes_procesados:
                omitidos += 1
                continue

            existente = db.query(Candidato).filter(
                Candidato.hash_archivo == hash_archivo
            ).first()

            if existente:
                omitidos += 1
                continue

            hashes_procesados.add(hash_archivo)

            texto = (extraer_texto_pdf(ruta)
                     if file.lower().endswith(".pdf")
                     else extraer_texto_docx(ruta))

            if not texto:
                omitidos += 1
                continue

            datos = estructurar_cv_inteligente(texto)


            texto_embedding = f"""
Perfil: {datos['perfil']}
Experiencia: {datos['experiencia']}
Educacion: {datos['educacion']}
Habilidades: {datos['habilidades']}
Formacion complementaria: {datos['formacion_complementaria']}
Contexto adicional: {texto[:2000]}
""".strip()

            textos_embeddings.append(texto_embedding)
            candidatos_temp.append({
                "nombre": file,
                "hash":   hash_archivo,
                "texto":  texto,
                "datos":  datos
            })

    if not textos_embeddings:
        total = db.query(Candidato).count()
        db.close()
        return {"insertados": 0, "omitidos": omitidos, "total_en_db": total}

    embeddings = embedding_model.encode(
        textos_embeddings,
        batch_size=32,
        show_progress_bar=True
    )

    for i, item in enumerate(candidatos_temp):
        candidato = Candidato(
            nombre=item["nombre"],
            nombre_archivo=item["nombre"],
            hash_archivo=item["hash"],
            texto_completo=item["texto"],
            perfil=item["datos"]["perfil"],
            experiencia=item["datos"]["experiencia"],
            educacion=item["datos"]["educacion"],
            habilidades=item["datos"]["habilidades"],
            formacion_complementaria=item["datos"]["formacion_complementaria"],
            embedding=json.dumps(embeddings[i].tolist())
        )
        db.add(candidato)
        insertados += 1

    db.commit()
    total = db.query(Candidato).count()
    db.close()

    return {"insertados": insertados, "omitidos": omitidos, "total_en_db": total}