import streamlit as st
import requests

st.title("Dashboard de Candidatos")

if st.button("Actualizar información"):

    try:
        response = requests.post("http://127.0.0.1:8000/actualizar")

        if response.status_code == 200:
            data = response.json()
            st.success(data.get("mensaje", "Proceso completado"))
        else:
            st.error(f"Error {response.status_code}")
            st.text(response.text)

    except Exception as e:
        st.error("No se pudo conectar con el backend")
