import streamlit as st
# Usa:
from dashboard import mostrar_dashboard  # Si dashboard.py está en la misma carpeta
# O
import dashboard  # y luego dashboard.mostrar_dashboard()
st.set_page_config(
    page_title="Bolsa de Empleo UTP",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="collapsed"  # ← así arranca cerrado y se abre con la flechita
)

# ── Importar páginas ──
from login import mostrar_login
from dashboard import mostrar_dashboard

# ── Control de sesión ──
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "usuario" not in st.session_state:
    st.session_state["usuario"] = None

# ── Enrutamiento ──
if not st.session_state["autenticado"]:
    mostrar_login()
else:
    mostrar_dashboard()