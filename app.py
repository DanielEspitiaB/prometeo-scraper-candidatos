"""
Prometeo Talent — Consola de candidatos.

Punto de entrada: menú de navegación SUPERIOR con las dos secciones:
  - Extractor de candidatos (scraping LinkedIn -> Excel/CSV)
  - Enviar a Teamtailor (CSV -> vacante del ATS)
"""

import streamlit as st

st.set_page_config(
    page_title="Prometeo Talent — Consola de candidatos",
    page_icon="🔥",
    layout="centered",
)

pg = st.navigation(
    [
        st.Page("vistas/extractor.py", title="Extractor de candidatos", icon="🔍", default=True),
        st.Page("vistas/enviar_teamtailor.py", title="Enviar a Teamtailor", icon="📤"),
    ],
    position="top",
)
pg.run()
