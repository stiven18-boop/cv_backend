import streamlit as st
import requests
import time
import base64
import re
from html import escape as he
from escaner import mostrar_escaner
import os



API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# ── Helpers ──────────────────────────────────────────────────────
def encode_image(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return ""


_HEADERS = re.compile(
    r"^\s*("
    r"PERFIL(\s*(LABORAL|PROFESIONAL))?|"
    r"EXPERIENCIA(\s*(LABORAL|PROFESIONAL))?|"
    r"EDUCACI[OÓ]N(\s+INFORMAL)?|"
    r"NIVEL\s+EDUCATIVO|"
    r"FORMACI[OÓ]N\s*AC?AD[EÉ]MICA|"
    r"INFORMACI[OÓ]N\s*AC?AD[EÉ]MICA|"
    r"INFORMACI[OÓ]N\s*AC[AÁ]D[EÉ]MICA|"
    r"HABILIDADES|COMPETENCIAS|APTITUDES|"
    r"DATOS\s*PERSONALES|INFORMACI[OÓ]N\s*PERSONAL|"
    r"IDIOMAS(\s*Y\s*OTROS\s*CONOCIMIENTOS)?|"
    r"REFERENCIAS(\s*(LABORALES|PERSONALES|FAMILIARES))?|"
    r"OBJETIVO\s*PROFESIONAL|SOBRE\s*M[IÍ]"
    r")\s*$",
    re.IGNORECASE | re.MULTILINE
)


def limpiar(texto: str) -> str:
    if not texto:
        return ""
    lineas = []
    for l in texto.strip().splitlines():
        s = l.strip()
        if _HEADERS.match(s):
            continue
        if re.match(r'^:\s*', s):
            s = re.sub(r'^:\s*', '', s)
        if s:
            lineas.append(s)
    return "\n".join(lineas).strip()


_ETIQUETAS_FORMULARIO = re.compile(
    r"^\s*(EMPRESA|TIEMPO\s+LABORADO|CARGO|JEFE\s+INMEDIATO|TELEFONOS?|"
    r"CONTRATO|DURACI[OÓ]N|COMO\s+DOCENTE|DIRECTOR\s+DE\s+TRABAJOS)\s*:?\s*$",
    re.IGNORECASE
)


def safe(val):
    txt = limpiar((val or "").strip())
    if not txt:
        return "—"

    lineas_raw = txt.splitlines()
    lineas = []
    for l in lineas_raw:
        s = l.strip()
        if _ETIQUETAS_FORMULARIO.match(s):
            continue
        if s in (":", "—", "-", "–"):
            continue
        if re.match(r'^[A-ZÁÉÍÓÚÑ\s]{3,25}$', s) and len(s.split()) <= 3 and not re.search(r'[,\.;]', s):
            continue
        if re.match(r'^C\.?C\.?\s*[\d\.,]+', s, re.IGNORECASE):
            continue
        lineas.append(s)

    resultado = he("\n".join(lineas))
    resultado = resultado.replace("\n\n", '<br><hr style="border:none;border-top:1px solid #e8f0f8;margin:6px 0;">')
    resultado = resultado.replace("\n", "<br>")
    return resultado


if "sidebar_open" not in st.session_state:
    st.session_state.sidebar_open = True




# ─────────────────────────────────────────────────────────────────
def mostrar_dashboard():
    logo_spe_b64 = encode_image(os.path.join(ASSETS_DIR,"logo.png"))
    logo_utp_b64 = encode_image(os.path.join(ASSETS_DIR,"bolsa_empleo.png"))
    logo_spe_src = f"data:image/png;base64,{logo_spe_b64}" if logo_spe_b64 else ""
    logo_utp_src = f"data:image/png;base64,{logo_utp_b64}" if logo_utp_b64 else ""
    logo_aseutp_b64 = encode_image(os.path.join(ASSETS_DIR,"ASEUTP.LOGO BLANCO-07.png"))
    logo_aseutp_src = f"data:image/png;base64,{logo_aseutp_b64}" if logo_aseutp_b64 else ""
    logo2_utp = encode_image(os.path.join(ASSETS_DIR,"UTP.png"))
    logo_utp2_src = f"data:image/png;base64,{logo2_utp}" if logo2_utp else ""
    usuario_actual = st.session_state.get("usuario", "Usuario")
    inicial = usuario_actual[0].upper() if usuario_actual else "U"

    if "sidebar_open" not in st.session_state:
        st.session_state.sidebar_open = True

    # ════════════════════════════════════════
    # ESTILOS GLOBALES
    # ════════════════════════════════════════
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

    [data-testid="collapsedControl"] svg, 
[data-testid="stSidebar"] svg,
button[kind="header"] svg {
    font-family: 'Material Icons' !important; /* O dejar que use la de defecto */
}
    .stApp { background: #ffffff !important; }
    #MainMenu, footer { visibility: hidden; }
    .block-container {
        padding: 1rem 1.5rem !important;
    }

    /* ── TOPBAR ── */
    .topbar {
        width: 100%;
        background: linear-gradient(95deg, #0d47a1 0%, #1565c0 55%, #1976d2 100%);
        height: 64px; padding: 0 2.5rem;
        display: flex; align-items: center; justify-content: space-between;
        box-shadow: 0 2px 18px rgba(13,71,161,0.28);
    }


    /* ── Flechita nativa de Streamlit: visible y estilizada ── */
    button[data-testid="baseButton-headerNoPadding"],
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        border: none !important;
        border-radius: 0 10px 10px 0 !important;
        width: 26px !important;
        min-width: 26px !important;
        box-shadow: 3px 2px 10px rgba(21,101,192,0.4) !important;
        z-index: 999999 !important;
    }
    button[data-testid="baseButton-headerNoPadding"] svg,
    [data-testid="collapsedControl"] svg {
    fill: white !important;
    color: white !important;
}
    .tb-left  { display:flex; align-items:center; gap:1.2rem; }
    .tb-left img { height:38px; object-fit:contain; }
    .logo-utp, .logo-spe { filter: brightness(0) invert(1); }
    .logo-aseutp { filter: none; height: 42px; }
    .tb-sep   { width:1px; height:28px; background:rgba(255,255,255,0.2); }
    .tb-brand b     { font-size:.95rem; font-weight:800; color:#fff; display:block; letter-spacing:-.01em; }
    .tb-brand small { font-size:.6rem;  color:rgba(255,255,255,.6); letter-spacing:.12em; text-transform:uppercase; }
    .tb-right { display:flex; align-items:center; gap:.8rem; }
    .tb-chip  { display:flex; align-items:center; gap:6px; background:rgba(255,255,255,.13);
                border:1px solid rgba(255,255,255,.22); border-radius:30px; padding:4px 12px 4px 6px; }
    .tb-av    { width:24px; height:24px; border-radius:50%; background:linear-gradient(135deg,#42a5f5,#90caf9);
                display:flex; align-items:center; justify-content:center;
                font-size:.68rem; font-weight:800; color:#0d47a1; }
    .tb-nm    { font-size:.78rem; font-weight:600; color:#fff; }

    /* ── Logout ── */
    .logout-w .stButton > button {
        background:transparent !important; border:1px solid rgba(255,255,255,.25) !important;
        border-radius:30px !important; color:rgba(255,255,255,.8) !important;
        font-size:.72rem !important; padding:3px 12px !important;
        box-shadow:none !important; width:auto !important; margin-top:4px !important;
    }
    .logout-w .stButton > button:hover {
        background:rgba(220,53,69,.18) !important; border-color:#f48fb1 !important;
        color:#ffcdd2 !important; transform:none !important; box-shadow:none !important;
    }

    /* ── TABS personalizados ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: #f0f5fb;
        border-radius: 12px;
        padding: 6px 8px;
        margin-bottom: 1rem;
        border: 1.5px solid #dce8f7;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 700 !important;
        font-size: .85rem !important;
        color: #607d8b !important;
        padding: 8px 20px !important;
        border: none !important;
        background: transparent !important;
        transition: all .2s !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #1565c0, #1976d2) !important;
        color: #ffffff !important;
        box-shadow: 0 3px 10px rgba(21,101,192,.3) !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
    }

    /* ── SIDEBAR panel ── */
    .sb-panel {
        background: #ffffff;
        border-radius: 16px;
        border: 1.5px solid #dce8f7;
        padding: 1.6rem 1.4rem 1.8rem;
        box-shadow: 0 2px 16px rgba(13,71,161,.06);
        margin: 1.2rem 0 1.2rem 1.5rem;
    }
    .sec-lbl {
        font-size:.62rem; font-weight:800; letter-spacing:.2em;
        text-transform:uppercase; color:#90a4ae;
        display:flex; align-items:center; gap:8px; margin:0 0 .85rem;
    }
    .sec-lbl::after { content:''; flex:1; height:1px; background:#e8f0f8; }
    .sb-div { height:1px; background:linear-gradient(90deg,#e0ecf8,transparent); margin:1.1rem 0; }

    /* Sync card */
    .sync-card {
        background:linear-gradient(135deg,#e3f2fd,#f0f8ff);
        border:1.5px solid #90caf9; border-radius:12px;
        padding:.9rem 1rem; margin-bottom:.9rem; position:relative; overflow:hidden;
    }
    .sync-card::before {
        content:''; position:absolute; top:0; left:0; right:0; height:3px;
        background:linear-gradient(90deg,#1565c0,#42a5f5);
    }
    .sync-card b   { font-size:.8rem; color:#1565c0; display:block; margin-bottom:.2rem; }
    .sync-card p   { font-size:.72rem; color:#607d8b; margin:0; line-height:1.5; }

    /* Botones generales */
    .stButton > button {
        width:100% !important;
        background:linear-gradient(135deg,#1565c0,#1e88e5) !important;
        color:#fff !important; border:none !important; border-radius:10px !important;
        font-family:'Plus Jakarta Sans',sans-serif !important;
        font-weight:700 !important; font-size:.83rem !important;
        padding:.58rem 1rem !important;
        box-shadow:0 3px 12px rgba(21,101,192,.3) !important;
        transition:all .18s !important; letter-spacing:.01em !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #1565c0, #f4b400) !important;
    }

    /* Botones modo tab */
    .tab-active .stButton > button {
        background:#1565c0 !important;
        box-shadow:0 2px 8px rgba(21,101,192,.25) !important;
    }
    .tab-inactive .stButton > button {
        background:#f0f5fb !important; color:#607d8b !important;
        box-shadow:none !important; border:1.5px solid #dce8f7 !important;
    }
    .tab-inactive .stButton > button:hover {
        background:#e3f2fd !important; color:#1565c0 !important;
        transform:none !important;
    }

    /* Sync button */
    .sync-w .stButton > button {
        background:linear-gradient(135deg,#1565c0,#1976d2) !important;
        font-size:.78rem !important; padding:.48rem .9rem !important;
        box-shadow:0 2px 8px rgba(21,101,192,.25) !important;
    }

    /* Inputs */
    .stTextInput > div > div > input {
        background:#f7faff !important; border:1.5px solid #d0e4f7 !important;
        border-radius:9px !important; color:#1a2a3a !important;
        font-family:'Plus Jakarta Sans',sans-serif !important;
        font-size:.83rem !important; padding:.52rem .8rem !important;
        transition:all .18s !important;
    }
    .stTextInput > div > div > input:focus {
        border-color:#1976d2 !important; background:#fff !important;
        box-shadow:0 0 0 3px rgba(25,118,210,.1) !important;
    }
    .stTextInput > label {
        color:#455a64 !important; font-size:.66rem !important;
        font-weight:700 !important; letter-spacing:.12em !important;
        text-transform:uppercase !important;
    }

    /* Selectbox */
    .stSelectbox > label {
        color:#455a64 !important; font-size:.66rem !important;
        font-weight:700 !important; letter-spacing:.12em !important;
        text-transform:uppercase !important;
    }

    /* ── ÁREA DE RESULTADOS ── */
    .res-area { padding: 1.2rem 1.5rem 1.2rem .5rem; }

    /* Header resultados */
    .res-hdr {
        display:flex; align-items:center; justify-content:space-between;
        margin-bottom:1.2rem; padding:.9rem 1rem; border-radius:12px;
        background:#f7faff; border:1.5px solid #dce8f7;
    }
    .res-hdr-title { font-size:1.05rem; font-weight:800; color:#0d47a1; margin:0; }
    .res-badge {
        background:#e3f2fd; color:#1565c0; border:1px solid #90caf9;
        border-radius:20px; padding:3px 12px;
        font-size:.7rem; font-weight:700; letter-spacing:.06em;
    }

    /* Empty state */
    .empty-st {
        display:flex; flex-direction:column; align-items:center;
        justify-content:center; min-height:55vh; text-align:center; gap:.9rem;
    }
    .empty-ico {
        width:72px; height:72px; border-radius:50%;
        background:linear-gradient(135deg,#e3f2fd,#bbdefb);
        display:flex; align-items:center; justify-content:center;
        font-size:1.8rem; box-shadow:0 4px 16px rgba(21,101,192,.1);
    }
    .empty-t { font-size:1rem; font-weight:700; color:#1565c0; margin:0; }
    .empty-s { font-size:.78rem; color:#90a4ae; margin:0; max-width:240px; line-height:1.6; }

    /* ── EXPANDER (candidato) ── */
    .stExpander {
        border: 1.5px solid #dce8f7 !important;
        border-radius: 14px !important;
        background: #ffffff !important;
        margin-bottom: .85rem !important;
        box-shadow: 0 2px 10px rgba(13,71,161,.05) !important;
        overflow: hidden !important;
    }
    .stExpander:hover { transform: translateY(-2px); transition: all .2s ease; }
    .stExpander > details > summary {
        background: linear-gradient(135deg,#f0f6ff,#e8f2ff) !important;
        padding: .9rem 1.2rem !important; border-radius: 13px !important;
        cursor: pointer !important; list-style: none !important;
    }
    .stExpander > details[open] > summary {
        border-radius: 13px 13px 0 0 !important;
        border-bottom: 1.5px solid #dce8f7 !important;
    }
    .stExpander summary p {
        color: #0d47a1 !important; font-weight: 700 !important; font-size: .92rem !important;
    }
    .stExpander > details > div[data-testid="stExpanderDetails"] {
        padding: 1.1rem 1.3rem !important; background: #ffffff !important;
    }

    /* Grid de campos CV */
    .cv-grid { display:grid; grid-template-columns:1fr 1fr; gap:.85rem; margin-top:.3rem; }
    .cv-f.full { grid-column:1/-1; }
    .cv-flbl {
        font-size:.6rem; font-weight:800; letter-spacing:.18em;
        text-transform:uppercase; color:#1565c0;
        display:flex; align-items:center; gap:6px; margin-bottom:5px;
    }
    .cv-flbl::after { content:''; flex:1; height:1px; background:#e3edf7; }
    .cv-fval {
        font-size:.81rem; color:#37474f; line-height:1.65;
        background:#f7faff; border-radius:8px;
        padding:.6rem .8rem; border:1px solid #e8f0f8; min-height:44px;
        max-height:280px; overflow-y:auto;
    }
    .cv-fval.empty { color:#b0bec5; font-style:italic; }
    .cv-fval hr { border:none; border-top:1px dashed #d0e4f7; margin:8px 0; }

    /* Footer de la card */
    .cv-foot {
        margin-top:1rem; padding-top:.85rem;
        border-top:1px solid #e8f0f8; display:flex; justify-content:flex-end;
    }
    .dl-btn {
        display:inline-flex; align-items:center; gap:6px;
        background:linear-gradient(135deg,#1565c0,#1976d2);
        color:#fff !important; text-decoration:none !important;
        font-size:.75rem !important; font-weight:700 !important;
        padding:7px 16px; border-radius:8px;
        box-shadow:0 3px 10px rgba(21,101,192,.28);
        transition:all .18s; letter-spacing:.02em;
    }
    .dl-btn:hover {
        background:linear-gradient(135deg,#0d47a1,#1565c0) !important;
        box-shadow:0 5px 16px rgba(21,101,192,.38) !important;
        transform:translateY(-1px);
    }

    /* Alerts */
    .stAlert { border-radius:10px !important; font-size:.82rem !important; border-width:1.5px !important; }
    div[data-baseweb="notification"] { background:#E3F2FD !important; border:1.5px solid #64B5F6 !important; }
    div[data-baseweb="notification"] p { color:#0D47A1 !important; font-weight:600; }
    .stAlert[data-testid="stAlert-success"] { background:#E8F5E9 !important; border:1.5px solid #66BB6A !important; color:#1B5E20 !important; }
    .stSpinner > div { border-top-color:#1976D2 !important; }
    .stSpinner p { color:#0D47A1 !important; font-weight:600 !important; }
    .stAlert[data-testid="stAlert-warning"] { background:#FFF8E1 !important; border:1.5px solid #FFB300 !important; color:#E65100 !important; }
    .stAlert[data-testid="stAlert-error"] { background:#FDECEA !important; border:1.5px solid #EF5350 !important; color:#B71C1C !important; }

    /* Animación entrada */
    .stExpander { animation: fadeSlide .35s ease; }
    @keyframes fadeSlide { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:translateY(0); } }

    /* Alerts compactas */
    .stAlert { padding:0.35rem 0.6rem !important; font-size:0.72rem !important; border-radius:7px !important; line-height:1.2 !important; }
    .stAlert svg { width:14px !important; height:14px !important; }

    /* Progress bar compacta */
    .stProgress > div > div { height:6px !important; border-radius:6px !important; }

    /* Sidebar fija */
    .sb-panel { position:sticky; top:90px; }

    /* KPI cards */
    .kpi-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:1rem; }
    .kpi-card { background:#ffffff; border:1.5px solid #dce8f7; border-radius:12px; padding:.8rem 1rem; box-shadow:0 2px 10px rgba(13,71,161,.06); }
    .kpi-title { font-size:.65rem; text-transform:uppercase; letter-spacing:.15em; color:#90a4ae; }
    .kpi-value { font-size:1.1rem; font-weight:800; color:#1565c0; }

    /* Buscador ATS */
    .ats-search { background:linear-gradient(135deg,#f7faff,#eef4ff); border:1.5px solid #dce8f7; border-radius:10px; padding:.6rem .8rem; margin-bottom:.8rem; color:#0d47a1; font-size:.82rem; }
    .ats-search b { color:#0d47a1; font-weight:700; }

    /* Variables */
    :root { --primary: #1565c0; --secondary: #1976d2; --accent-gold: #f4b400; }

    /* Skeleton */
    .skeleton { background:linear-gradient(90deg,#f1f5fb 25%,#e3edf7 37%,#f1f5fb 63%); background-size:400% 100%; animation:skeleton 1.4s ease infinite; height:60px; border-radius:10px; margin-bottom:8px; }
    @keyframes skeleton { 0%{background-position:100% 50%} 100%{background-position:0 50%} }

    /* Scrollbar */
    ::-webkit-scrollbar { width:5px; height:5px; }
    ::-webkit-scrollbar-track { background:transparent; }
    ::-webkit-scrollbar-thumb { background:#90caf9; border-radius:10px; }

    /* ── SIDEBAR: sin espacio reservado cuando está cerrado ── */
    [data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 240px !important;
        max-width: 240px !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] {
    min-width: 0px !important;
    width: 0px !important;
}
/* Color blanco para el icono de la flecha */
[data-testid="collapsedControl"] {
    background-color: #1565c0 !important;
    border-radius: 0 8px 8px 0 !important;
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 1000000 !important;
}

/* El SVG que Streamlit inyecta usa currentColor — hay que forzarlo */
[data-testid="collapsedControl"] svg {
    fill: #ffffff !important;
    color: #ffffff !important;
}

/* Algunos íconos usan path en lugar de fill directo */
[data-testid="collapsedControl"] svg path {
    fill: #ffffff !important;
    stroke: #ffffff !important;



    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="topbar">
      <div class="tb-left">
        {"<img class='logo_utp2_src' src='" + logo_utp2_src + "'>" if logo_utp2_src else ""}
        {"<div class='logo-sep'></div>" if logo_utp2_src and logo_aseutp_src else ""}
        {"<img class='logo-aseutp' src='" + logo_aseutp_src + "'>" if logo_aseutp_src else ""}
        {"<div class='logo-sep'></div>" if logo_aseutp_src and logo_spe_src else ""}
        {"<img class='logo-utp' src='" + logo_utp_src + "'>" if logo_utp_src else ""}
        {"<div class='logo-sep'></div>" if logo_utp_src and logo_aseutp_src else ""}
        {"<img class='logo-spe' src='" + logo_spe_src + "'>" if logo_spe_src else ""}
        <div class="tb-brand">
          <b>Dashboard de Candidatos</b>
          <small>Gestión de Egresados</small>
        </div>
      </div>
      <div class="tb-right">
        <div class="tb-chip">
          <div class="tb-av">{inicial}</div>
          <span class="tb-nm">{usuario_actual}</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════
    # SIDEBAR DE NAVEGACIÓN (100% Python)
    # ════════════════════════════════════════
    st.markdown("""
    <style>
    /* Sidebar azul */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d47a1 0%, #1565c0 60%, #1976d2 100%) !important;
    }
    [data-testid="stSidebar"] * { color: #ffffff !important; }

    /* Radio como menú */
    [data-testid="stSidebar"] .stRadio > div { gap: 4px !important; }
    [data-testid="stSidebar"] .stRadio label {
        background: rgba(255,255,255,0.08) !important;
        border-radius: 10px !important;
        padding: 10px 14px !important;
        width: 100% !important;
        cursor: pointer !important;
        transition: all .18s !important;
        border: 1px solid transparent !important;
        font-size: .85rem !important;
        font-weight: 600 !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] .stRadio label:hover {
        background: rgba(255,255,255,0.18) !important;
        border-color: rgba(255,255,255,0.3) !important;
    }
    /* Ocultar círculo del radio */
    [data-testid="stSidebar"] .stRadio label > div:first-child { display: none !important; }
    [data-testid="stSidebar"] .stRadio label p,
    [data-testid="stSidebar"] .stRadio [data-testid="stMarkdownContainer"] p {
        color: #ffffff !important;
        font-size: .85rem !important;
        font-weight: 600 !important;
        visibility: visible !important;
        opacity: 1 !important;
    }
    /* Botón logout */
    [data-testid="stSidebar"] .stButton > button {
        background: rgba(220,53,69,0.25) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        color: #ffcdd2 !important;
        font-size: .78rem !important;
        border-radius: 10px !important;
        padding: 8px 12px !important;
        box-shadow: none !important;
        margin-top: 1rem !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(220,53,69,0.45) !important;
    }
    /* Botón nativo de colapsar/expandir sidebar — hacerlo visible */
    [data-testid="collapsedControl"],
    button[kind="header"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        background: #1565c0 !important;
        color: #ffffff !important;
        border-radius: 0 8px 8px 0 !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem !important;
    }

    header[data-testid="stHeader"] {
    background: transparent !important;
    box-shadow: none !important;
}

[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    z-index: 1000000 !important;
    background-color: #1565c0 !important; /* Azul de tu marca */
    color: #000000 !important;
    border-radius: 0 8px 8px 0 !important;
    left: 0 !important;
    top: 10px !important;
}


    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        if logo_aseutp_src:
            st.markdown(f"""
    <div style="text-align:center; padding: .8rem 0 1rem; border-bottom:1px solid rgba(255,255,255,0.15); margin-bottom:1rem;">
        <img class="logo-spe" src="{logo_aseutp_src}" style="height:60px; margin-bottom:6px;">
        <div style="font-size:.6rem; font-weight:800; letter-spacing:.15em; text-transform:uppercase; color:rgba(255,255,255,0.55);">
            Gestión de Egresados
        </div>
    </div>
    """, unsafe_allow_html=True)

        st.markdown(
            '<p style="font-size:.6rem;font-weight:800;letter-spacing:.2em;text-transform:uppercase;color:rgba(255,255,255,0.5);margin:0 0 .6rem;">Navegación</p>',
            unsafe_allow_html=True)

        pagina = st.radio(
            label="pagina",
            options=["🏠  Dashboard de Candidatos", "🔍  Escáner de Egresados"],
            key="pagina_actual",
            label_visibility="collapsed"
        )

        st.markdown("<br>" * 6, unsafe_allow_html=True)
        st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.15);margin:0 0 .8rem;">',
                    unsafe_allow_html=True)

        if st.button("⎋  Cerrar sesión", key="logout_sidebar"):
            st.session_state["autenticado"] = False
            st.session_state["usuario"] = None
            st.rerun()

    # ── Enrutamiento ──
    if pagina == "🏠  Dashboard de Candidatos":
        _mostrar_dashboard_contenido()
    else:
        mostrar_escaner()


# ─────────────────────────────────────────────────────────────────
# Contenido principal del Dashboard (separado para usar con tabs)
# ─────────────────────────────────────────────────────────────────
def _mostrar_dashboard_contenido():
    # ════════════════════════════════════════
    # LAYOUT: 35% sidebar | 65% resultados
    # ════════════════════════════════════════
    col_sb, col_res = st.columns([1.3, 2.7], gap="small")

    # ────────────────────────────────────────
    # SIDEBAR
    # ────────────────────────────────────────
    with col_sb:
        st.markdown('<div class="sb-panel">', unsafe_allow_html=True)

        # Sincronización
        st.markdown('<p class="sec-lbl">Sincronización</p>', unsafe_allow_html=True)
        st.markdown("""
        <div class="sync-card">
          <b>🔄 Actualizar base de datos</b>
          <p>Descarga y procesa los CVs más recientes.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sync-w">', unsafe_allow_html=True)
        if st.button("⚡ Sincronizar ahora"):
            try:
                r = requests.post(f"{API_URL}/actualizar", timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("status") == "en_proceso":
                        st.info("⏳ Ya hay una actualización en curso.")
                    else:
                        st.info("⏳ Sincronización iniciada. Procesando CVs...")
                        st.session_state["actualizando"] = True
                else:
                    st.error(f"Error {r.status_code}")
            except Exception as e:
                st.error(f"❌ {e}")
        st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.get("actualizando"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i in range(120):
                time.sleep(3)
                try:
                    r = requests.get(f"{API_URL}/actualizar/estado", timeout=10)
                    est = r.json()

                    progreso = min((i + 1) / 120, 1.0)
                    progress_bar.progress(progreso)
                    status_text.info("📄 Procesando archivos...")

                    if est.get("status") == "completado":
                        st.session_state["ultimos_insertados"] = est.get("insertados", 0)
                        st.session_state["total_cvs"] = est.get("total_en_db", 0)
                        progress_bar.progress(1.0)
                        st.success(f"✅ Insertados: {est.get('insertados', 0)} · Total: {est.get('total_en_db', 0)}")
                        st.session_state["actualizando"] = False
                        break
                    elif est.get("status") == "error":
                        st.error(f"❌ {est.get('detalle')}")
                        st.session_state["actualizando"] = False
                        break
                    if i == 100:
                        st.warning("⏱ La sincronización está tardando más de lo esperado.")
                except:
                    break

        st.markdown('<div class="sb-div"></div>', unsafe_allow_html=True)

        if "modo" not in st.session_state:
            st.session_state["modo"] = "semantica"




        st.markdown('<div class="sb-div"></div>', unsafe_allow_html=True)

        # Campos de búsqueda
        modo = st.session_state["modo"]
        st.markdown("""
        <div class="ats-search">
        🔎 <b>Búsqueda inteligente de candidatos</b>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<p class="sec-lbl">Criterios de búsqueda</p>', unsafe_allow_html=True)

        if modo == "semantica":
            titulo = st.text_input("Cargo / Título", placeholder="Ej: Ingeniero, Docente...")
            experiencia = st.text_input("Experiencia", placeholder="Ej: soldadura, diseño...")
            habilidad = st.text_input("Habilidad", placeholder="Ej: AutoCAD, liderazgo...")
        else:
            termino = st.text_input("Término exacto", placeholder="Ej: Python, SENA, mecánica...")

        st.markdown('<div class="sb-div"></div>', unsafe_allow_html=True)
        st.markdown('<p class="sec-lbl">Filtros académicos</p>', unsafe_allow_html=True)

        universidad = st.text_input("Universidad / Institución", placeholder="Ej: UTP, SENA, UNAD...")
        nivel = st.selectbox("Nivel de estudio", [
            "Todos los niveles",
            "Bachiller",
            "Técnico",
            "Tecnólogo",
            "Profesional / Pregrado",
            "Especialización",
            "Maestría / Magíster",
            "Doctorado / PhD",
        ])

        st.markdown('<div class="sb-div"></div>', unsafe_allow_html=True)

        if st.button("🔍  Buscar candidatos"):
            params = {}

            if modo == "semantica":
                if not any([titulo, experiencia, habilidad,
                            universidad.strip(), nivel != "Todos los niveles"]):
                    st.warning("Ingresa al menos un criterio.")
                    st.stop()
                params["umbral"] = 0.10
                if titulo:      params["titulo"] = titulo
                if experiencia: params["experiencia"] = experiencia
                if habilidad:   params["habilidad"] = habilidad
                endpoint = f"{API_URL}/buscar"
            else:
                if not termino.strip():
                    st.warning("Escribe un término.")
                    st.stop()
                params["termino"] = termino.strip()
                endpoint = f"{API_URL}/buscar-texto"

            if universidad.strip():
                params["universidad"] = universidad.strip()
            if nivel != "Todos los niveles":
                params["nivel"] = nivel

            with st.spinner("Buscando..."):
                try:
                    r = requests.get(endpoint, params=params, timeout=30)
                    st.session_state["resultados"] = (
                        r.json() if r.status_code == 200 else {"error": r.text}
                    )
                except Exception as e:
                    st.session_state["resultados"] = {"error": str(e)}

        st.markdown('</div>', unsafe_allow_html=True)  # cierra sb-panel

    # ────────────────────────────────────────
    # PANEL RESULTADOS
    # ────────────────────────────────────────
    with col_res:

        # ── KPI CARDS ──
        total_cvs = st.session_state.get("total_cvs", 0)
        ultimos_insertados = st.session_state.get("ultimos_insertados", 0)
        resultados_actuales = len(st.session_state.get("resultados", [])) if isinstance(
            st.session_state.get("resultados"), list) else 0

        st.markdown(f"""
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-title">CVs en base</div>
            <div class="kpi-value">{total_cvs}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">Última sincronización</div>
            <div class="kpi-value">{ultimos_insertados}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">Resultados actuales</div>
            <div class="kpi-value">{resultados_actuales}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="res-area">', unsafe_allow_html=True)

        data = st.session_state.get("resultados", None)

        if data is None:
            st.markdown("""
            <div class="empty-st">
              <div class="empty-ico">🔍</div>
              <p class="empty-t">Realiza tu primera búsqueda</p>
              <p class="empty-s">Completa los criterios en el panel izquierdo y presiona "Buscar candidatos".</p>
            </div>
            """, unsafe_allow_html=True)

        elif isinstance(data, dict) and "error" in data:
            st.error(f"❌ {data['error']}")

        elif isinstance(data, list) and len(data) == 0:
            st.markdown("""
            <div class="empty-st">
              <div class="empty-ico">😶</div>
              <p class="empty-t">Sin resultados</p>
              <p class="empty-s">No se encontraron candidatos. Intenta con otros términos o amplía los filtros.</p>
            </div>
            """, unsafe_allow_html=True)

        elif isinstance(data, list):

            ids_resultados = [str(c["id"]) for c in data if isinstance(c, dict) and c.get("id")]

            st.markdown(f"""
            <div class="res-hdr">
              <p class="res-hdr-title">Hojas de vida encontradas</p>
              <div style="display:flex; align-items:center; gap:.8rem;">
                <span class="res-badge">{len(data)} candidato{"s" if len(data) != 1 else ""}</span>
                {"" if not ids_resultados else f'<a class="dl-btn" href="{API_URL}/descargar-lote?ids={chr(44).join(ids_resultados)}" download="hojas_de_vida.zip" style="font-size:.72rem;padding:5px 14px;">📦 Descargar todos ({len(ids_resultados)})</a>'}
              </div>
            </div>
            """, unsafe_allow_html=True)

            for i, c in enumerate(data):
                if not isinstance(c, dict): continue

                nombre = (c.get("nombre", "Sin nombre") or "Sin nombre").strip()
                archivo = (c.get("archivo", nombre) or nombre).strip()
                cid = c.get("id", "")

                perfil_v = limpiar(c.get("perfil") or "")
                experiencia_v = limpiar(c.get("experiencia") or "")
                educacion_v = limpiar(c.get("educacion") or "")
                habilidades_v = limpiar(c.get("habilidades") or "")

                with st.expander(f"👤  {nombre}", expanded=False):

                    st.markdown(f"""
                    <div style="margin-bottom:.9rem; padding-bottom:.7rem; border-bottom:1px solid #e8f0f8;">
                      <span style="font-size:.65rem;font-weight:700;letter-spacing:.14em;
                                   text-transform:uppercase;color:#90a4ae;">Archivo</span>
                      <p style="font-family:monospace;font-size:.72rem;color:#607d8b;margin:2px 0 0;">{he(archivo)}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown('<div class="cv-grid">', unsafe_allow_html=True)

                    cls_p = "" if perfil_v else " empty"
                    st.markdown(f"""
                    <div class="cv-f full">
                      <div class="cv-flbl">Perfil profesional</div>
                      <div class="cv-fval{cls_p}">{safe(c.get("perfil"))}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    cls_e = "" if experiencia_v else " empty"
                    cls_d = "" if educacion_v else " empty"
                    st.markdown(f"""
                    <div class="cv-f">
                      <div class="cv-flbl">Experiencia laboral</div>
                      <div class="cv-fval{cls_e}">{safe(c.get("experiencia"))}</div>
                    </div>
                    <div class="cv-f">
                      <div class="cv-flbl">Educación</div>
                      <div class="cv-fval{cls_d}">{safe(c.get("educacion"))}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    form_comp_v = limpiar(c.get("formacion_complementaria") or "")
                    if form_comp_v:
                        st.markdown(f"""
                        <div class="cv-f full">
                          <div class="cv-flbl">Formación complementaria</div>
                          <div class="cv-fval">{safe(c.get("formacion_complementaria"))}</div>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown('</div>', unsafe_allow_html=True)  # cierra cv-grid

                    cls_h = "" if habilidades_v else " empty"
                    st.markdown(f"""
                    <div class="cv-f full">
                      <div class="cv-flbl">Habilidades</div>
                      <div class="cv-fval{cls_h}">{safe(c.get("habilidades"))}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    if cid:
                        st.markdown(f"""
                        <div class="cv-foot">
                          <a class="dl-btn" href="{API_URL}/descargar/{cid}" target="_blank">
                            📥 Descargar hoja de vida
                          </a>
                        </div>
                        """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)  # cierra res-area