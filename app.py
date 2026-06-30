"""
Prometeo Talent — Extractor de datos de candidatos (Streamlit).

Flujo simple:
    pegar URLs de LinkedIn  ->  raspar con Apify  ->  descargar Excel con los datos.

No hay chat ni evaluacion en esta version (esa logica sigue guardada en
evaluar.py / scorecard.py por si se reactiva mas adelante).
"""

import io
import re

import streamlit as st
import evaluar  # utilidades de scraping y perfil limpio

# Detecta URLs de perfiles de LinkedIn dentro de cualquier texto (CSV o pegado)
PATRON_URL = re.compile(r"(?:https?://)?(?:[\w-]+\.)*linkedin\.com/in/[^\s,;\"'\]\)]+", re.IGNORECASE)


def extraer_urls(texto: str) -> list:
    """Saca todas las URLs de perfil de LinkedIn de un texto, sin duplicados."""
    encontradas, vistos = [], set()
    for cruda in PATRON_URL.findall(texto or ""):
        url = cruda.strip().rstrip("/")
        if not url.lower().startswith("http"):
            url = "https://" + url
        clave = url.lower()
        if clave not in vistos:
            vistos.add(clave)
            encontradas.append(url)
    return encontradas

st.set_page_config(
    page_title="Prometeo Talent — Extractor de candidatos",
    page_icon="🔥",
    layout="centered",
)

LOGO = "https://cdn.prod.website-files.com/641dd5660616e8257e3f6375/641dd5660616e8af003f63da_Prometeo.png"

# ---------------------------------------------------------------------------
# Branding Prometeo (colores + tipografia Montserrat)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap');
      html, body, .stApp, [class*="css"] { font-family: 'Montserrat', sans-serif; }
      h1, h2, h3 { color: #142649; font-weight: 700; }
      .prometeo-bar {
        height: 6px;
        background: linear-gradient(90deg, #142649 0%, #0050BD 55%, #F49331 100%);
        border-radius: 4px; margin: 0.4rem 0 1.2rem 0;
      }
      .subtitulo { color: #758696; font-size: 0.95rem; margin-top: -0.4rem; }
      div.stButton > button[kind="primary"] {
        background-color: #F49331; border: none; color: white; font-weight: 600;
      }
      div.stButton > button[kind="primary"]:hover { background-color: #d97e22; color: white; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------
if "perfiles" not in st.session_state:
    st.session_state.perfiles = None

# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
st.image(LOGO, width=210)
st.markdown('<div class="prometeo-bar"></div>', unsafe_allow_html=True)
st.title("Extractor de candidatos")
st.markdown(
    '<p class="subtitulo">Pega las URLs de LinkedIn y descarga los datos de cada candidato en Excel.</p>',
    unsafe_allow_html=True,
)
st.write("")

# ---------------------------------------------------------------------------
# Verificar la llave de Apify
# ---------------------------------------------------------------------------
try:
    apify_ok = "APIFY_TOKEN" in st.secrets
except Exception:
    apify_ok = False

if not apify_ok:
    st.error("Falta `APIFY_TOKEN` en `.streamlit/secrets.toml`. Complétalo para poder extraer datos.")
    st.stop()

# ---------------------------------------------------------------------------
# Entrada de URLs
# ---------------------------------------------------------------------------
st.markdown("**Opción 1 — Pegar URLs** (una por línea)")
urls_texto = st.text_area(
    "URLs de LinkedIn",
    placeholder="https://www.linkedin.com/in/...\nhttps://www.linkedin.com/in/...",
    height=140,
    label_visibility="collapsed",
)

st.markdown("**Opción 2 — Subir un CSV** que contenga las URLs de LinkedIn")
archivo = st.file_uploader(
    "CSV con URLs", type=["csv"], label_visibility="collapsed",
)
st.caption(
    "Puedes usar cualquiera de las dos (o ambas). En el CSV detecto las URLs de LinkedIn "
    "automáticamente, sin importar en qué columna estén. Cada perfil cuesta ~$0.01 de Apify."
)

if st.button("📥 Extraer datos de candidatos", type="primary", use_container_width=True):
    texto = urls_texto or ""
    if archivo is not None:
        texto += "\n" + archivo.getvalue().decode("utf-8", errors="replace")
    urls = extraer_urls(texto)
    if not urls:
        st.warning(
            "No encontré URLs de LinkedIn. Pega los links arriba, o sube un CSV que tenga "
            "una columna con los links de los perfiles (deben contener `linkedin.com/in/`)."
        )
    else:
        try:
            barra = st.progress(0.0, text=f"Extrayendo {len(urls)} perfiles de LinkedIn...")

            def _progreso(hechos, total):
                barra.progress(hechos / total, text=f"Extrayendo... {hechos}/{total} perfiles")

            st.session_state.perfiles = evaluar.scrape_perfiles(
                urls, st.secrets["APIFY_TOKEN"], on_progress=_progreso
            )
            barra.progress(1.0, text="¡Listo!")
            st.success(f"Listo: {len(st.session_state.perfiles)} perfil(es) extraído(s) de {len(urls)} URL(s).")
        except Exception as e:
            st.error(f"Hubo un problema al extraer los datos: {e}")

# ---------------------------------------------------------------------------
# Resultados + descarga
# ---------------------------------------------------------------------------
perfiles = st.session_state.get("perfiles")
if perfiles:
    st.divider()
    st.subheader("Candidatos extraídos")

    tabla = []
    for crudo in perfiles:
        p = evaluar.perfil_limpio(crudo)
        c = evaluar.datos_contacto(crudo)
        tabla.append({
            "Nombre": p["nombre"],
            "Titular": (p["titular"] or "")[:70],
            "Ubicación": p["ubicacion"],
            "Años exp.": p["anios_experiencia_total"],
            "Email": c["email"] or "—",
            "LinkedIn": c["url"],
        })
    st.dataframe(tabla, use_container_width=True, hide_index=True)

    buffer = io.BytesIO()
    evaluar.construir_workbook_datos(perfiles).save(buffer)
    buffer.seek(0)
    st.caption("Para TODOS los datos (experiencia, skills, educación…), usa los botones de abajo. La tabla de arriba es solo un vistazo.")
    col_xlsx, col_csv = st.columns(2)
    with col_xlsx:
        st.download_button(
            "⬇️ Descargar Excel",
            data=buffer,
            file_name="candidatos_prometeo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col_csv:
        st.download_button(
            "⬇️ Descargar CSV completo",
            data=evaluar.construir_csv_datos(perfiles),
            file_name="candidatos_prometeo.csv",
            mime="text/csv",
            use_container_width=True,
        )
