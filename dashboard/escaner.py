import streamlit as st
import streamlit.components.v1 as components
import os

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")

def mostrar_escaner():
    """
    Renderiza el Escáner de Egresados (HTML + JS) dentro de la app Streamlit.
    No requiere inicio de sesión propio; está protegido por el login de la app.
    """

    st.markdown(
        """
        <style>
        /* Elimina el padding superior para que el iframe arranque más arriba */
        .block-container { padding-top: 1rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Ruta al HTML (mismo directorio que este archivo .py)
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escaner.html")

    if not os.path.exists(html_path):
        st.error(
            f"⚠️ No se encontró el archivo `escaner.html`.\n\n"
            f"Asegúrate de que esté en la misma carpeta que `escaner.py`:\n`{html_path}`"
        )
        return

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # height: ajusta según la resolución de tu pantalla.
    # scrolling=True permite scroll interno si el contenido es más largo.
    components.html(html_content, height=2200, scrolling=True)