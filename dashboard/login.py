import streamlit as st
import requests
import base64
import os

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

def encode_image(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return ""


def mostrar_login():
    logo_utp_b64 = encode_image(os.path.join(ASSETS_DIR,"bolsa_empleo.png"))
    logo_spe_b64 = encode_image(os.path.join(ASSETS_DIR,"logo.png"))
    logo_utp_src = f"data:image/png;base64,{logo_utp_b64}" if logo_utp_b64 else ""
    logo_spe_src = f"data:image/png;base64,{logo_spe_b64}" if logo_spe_b64 else ""
    logo_aseutp_b64 = encode_image(os.path.join(ASSETS_DIR,"ASEUTP.LOGO COLOR-05.png"))
    logo_aseutp_src = f"data:image/png;base64,{logo_aseutp_b64}" if logo_aseutp_b64 else ""
    logo1_utp = encode_image(os.path.join(ASSETS_DIR,"Logo_Azul.png"))
    logo_utp1_src = f"data:image/png;base64,{logo1_utp}" if logo1_utp else ""


    st.markdown(f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@300;400;600;700;900&family=Source+Sans+3:wght@300;400;600&display=swap');

      html, body, [class*="css"] {{
        font-family: 'Source Sans 3', sans-serif;
        background-color: #f0f4f8 !important;
        color: #1a2a3a;
      }}
      .stApp {{
        background-color: #f0f4f8 !important;
      }}
      #MainMenu, footer, header {{ visibility: hidden; }}
      .block-container {{
        padding-top: 0 !important;
        max-width: 100% !important;
      }}

      /* ── Fondo con patrón suave ── */
      .login-bg {{
        position: fixed;
        inset: 0;
        background:
          radial-gradient(ellipse 70% 60% at 20% 50%, rgba(21,101,192,0.08) 0%, transparent 60%),
          radial-gradient(ellipse 50% 70% at 80% 40%, rgba(25,118,210,0.05) 0%, transparent 60%),
          #f0f4f8;
        z-index: 0;
      }}
      .login-bg::after {{
        content: '';
        position: fixed;
        inset: 0;
        background-image:
          linear-gradient(rgba(21,101,192,0.04) 1px, transparent 1px),
          linear-gradient(90deg, rgba(21,101,192,0.04) 1px, transparent 1px);
        background-size: 48px 48px;
        pointer-events: none;
      }}

      /* ── Logos superiores ── */
      .login-logos {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 2.5rem;
        margin-bottom: 2.5rem;
        animation: fadeDown 0.6s ease both;
      }}

      .logo-sep {{
        width: 1px;
        height: 50px;
        background: linear-gradient(to bottom, transparent, #90caf9, transparent);
      }}

      .login-logos img {{
     height: 65px;
    object-fit: contain;
}}

/* Mantener color original */
      .login-logos .logo-aseutp {{
    height: 70px;
    filter: none;
}}

/* Logos blancos */
.login-logos .logo-utp,
.login-logos .logo-spe {{
    filter: none;
}}
.logo-utp {{
    height: 60px;
}}

.logo-aseutp {{
    height: 72px;
}}

.logo-spe {{
    height: 60px;
}}
      /* ── Card ── */
      .login-card-top {{
        background: linear-gradient(135deg, #1565c0 0%, #1976d2 100%);
        border-radius: 16px 16px 0 0;
        padding: 1.8rem 2.2rem 1.5rem;
        text-align: center;
        position: relative;
        overflow: hidden;
      }}
      .login-card-top::before {{
        content: '';
        position: absolute;
        inset: 0;
        background-image:
          linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px);
        background-size: 32px 32px;
      }}
      .login-card-body {{
        background: #ffffff;
        border: 1.5px solid #bbdefb;
        border-top: none;
        border-radius: 0 0 16px 16px;
        padding: 2rem 2.2rem 1.8rem;
        box-shadow: 0 8px 32px rgba(21,101,192,0.12);
        animation: fadeUp 0.7s ease 0.1s both;
      }}
      .login-title {{
        font-family: 'Source Sans 3', sans-serif;
        font-size: 1.5rem;
        font-weight: 900;
        color: #ffffff;
        margin: 0 0 0.3rem;
        letter-spacing: -0.02em;
        position: relative;
        z-index: 1;
      }}
      .login-subtitle {{
        font-size: 0.78rem;
        color: rgba(255,255,255,0.8);
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin: 0;
        position: relative;
        z-index: 1;
      }}
      
      .login-card-top {{
  margin-bottom: 16px;
}}

      /* ── Inputs ── */
      .stTextInput > div > div > input {{
        background: #f8fbff !important;
        border: 1.5px solid #90caf9 !important;
        border-radius: 10px !important;
        color: #1a2a3a !important;
        font-family: 'Source Sans 3', sans-serif !important;
        padding: 0.65rem 0.9rem !important;
        font-size: 0.95rem !important;
        transition: border-color 0.2s, box-shadow 0.2s;
      }}
      .stTextInput > div > div > input:focus {{
        border-color: #1976d2 !important;
        box-shadow: 0 0 0 3px rgba(25,118,210,0.12) !important;
        background: #ffffff !important;
      }}
      .stTextInput > label {{
        color: #1565c0 !important;
        font-size: 0.75rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
      }}

      /* ── Botón ── */
      .stButton > button {{
        background: linear-gradient(135deg, #1565c0 0%, #1976d2 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        font-family: 'Exo 2', sans-serif !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        letter-spacing: 0.06em !important;
        padding: 0.65rem 1.6rem !important;
        width: 100% !important;
        margin-top: 0.5rem !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 14px rgba(21,101,192,0.35) !important;
      }}
      .stButton > button:hover {{
        background: linear-gradient(135deg, #0d47a1 0%, #1565c0 100%) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px rgba(21,101,192,0.45) !important;
      }}

      /* ── Alerts ── */
      .stAlert {{
        background: #fff3e0 !important;
        border: 1px solid #ffb74d !important;
        border-radius: 10px !important;
        color: #e65100 !important;
      }}

      /* ── Footer ── */
      .login-footer {{
        margin-top: 1.5rem;
        text-align: center;
        color: #90a4ae;
        font-size: 0.73rem;
        letter-spacing: 0.06em;
      }}

      @keyframes fadeUp {{
        from {{ opacity: 0; transform: translateY(20px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
      }}
      @keyframes fadeDown {{
        from {{ opacity: 0; transform: translateY(-16px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
      }}
    </style>

    """, unsafe_allow_html=True)

    # ── Centrar con columnas ──
    _, col, _ = st.columns([1, 1.2, 1])

    with col:
        # Logos
        st.markdown(f"""
        <div class="login-logos">
  {"<img class='logo-aseutp' src='" + logo_utp1_src + "'>" if logo_utp1_src else ""}
  {"<div class='logo-sep'></div>" if logo_utp1_src and logo_utp1_src else ""}
  {"<img class='logo-aseutp' src='" + logo_aseutp_src + "'>" if logo_aseutp_src else ""}
  {"<div class='logo-sep'></div>" if logo_aseutp_src and logo_spe_src else ""}
  {"<img class='logo-utp' src='" + logo_utp_src + "'>" if logo_utp_src else ""}
  {"<div class='logo-sep'></div>" if logo_utp_src and logo_aseutp_src else ""}
  {"<img class='logo-spe' src='" + logo_spe_src + "'>" if logo_spe_src else ""}
</div>
        """, unsafe_allow_html=True)

        # Cabecera azul de la card
        st.markdown("""
        <div class="login-card-top">
          <p class="login-title">Iniciar Sesión</p>
          <p class="login-subtitle">Gestión de Bolsa de Empleo — Acceso restringido</p>
        </div>
        """, unsafe_allow_html=True)



        usuario = st.text_input("Usuario", placeholder="Tu nombre de usuario")
        contrasena = st.text_input("Contraseña", type="password", placeholder="••••••••")

        if st.button("→  Iniciar sesión"):
            if not usuario.strip() or not contrasena.strip():
                st.error("Por favor completa todos los campos.")
            else:
                try:
                    r = requests.post(
                        f"{API_URL}/auth/login",
                        json={"username": usuario.strip(), "password": contrasena.strip()},
                        timeout=10
                    )
                    if r.status_code == 200:
                        data = r.json()
                        st.session_state["autenticado"] = True
                        st.session_state["usuario"] = data.get("username", usuario)
                        st.rerun()
                    elif r.status_code == 401:
                        st.error("❌ Usuario o contraseña incorrectos.")
                    else:
                        st.error(f"Error del servidor ({r.status_code}).")
                except requests.exceptions.ConnectionError:
                    st.error("❌ No se pudo conectar con la API.")
                except Exception as e:
                    st.error(f"Error inesperado: {e}")

        st.markdown("""
        <div class="login-footer">
          Universidad Tecnológica de Pereira &nbsp;·&nbsp; Servicio Público de Empleo
        </div>
        </div>
        """, unsafe_allow_html=True)