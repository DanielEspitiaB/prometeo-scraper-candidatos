"""
Prometeo Talent — Enviar candidatos a Teamtailor.

Módulo aparte del extractor: subes un CSV con candidatos, eliges una vacante
(traída en vivo de Teamtailor: activas + unlisted, o pegando el ID), confirmas,
y los candidatos se crean y asocian a esa vacante. Con dedupe por email.
"""

import csv
import io
import unicodedata
from pathlib import Path

import streamlit as st

import teamtailor as tt

ASTRONAUTA = Path(__file__).resolve().parent.parent / "assets" / "astronauta.png"


LOGO = "https://cdn.prod.website-files.com/641dd5660616e8257e3f6375/641dd5660616e8af003f63da_Prometeo.png"

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
      div.stButton > button[kind="primary"] {
        background-color: #F49331; border: none; color: white; font-weight: 600;
      }
      div.stButton > button[kind="primary"]:hover { background-color: #d97e22; color: white; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.image(LOGO, width=210)
st.markdown('<div class="prometeo-bar"></div>', unsafe_allow_html=True)
st.title("Enviar candidatos a Teamtailor")

# Estado inicial: ilustración de bienvenida (solo antes de empezar el flujo)
if not st.session_state.get("tt_vacantes") and not st.session_state.get("tt_resultado"):
    _c1, _c2, _c3 = st.columns([1, 1.4, 1])
    with _c2:
        if ASTRONAUTA.exists():
            st.image(str(ASTRONAUTA), use_container_width=True)
        st.markdown(
            '<p style="text-align:center;color:#758696;font-weight:600;margin-top:-0.4rem;">'
            'Lanza tus candidatos a su próxima misión 🚀</p>',
            unsafe_allow_html=True,
        )
    st.write("")

# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------
try:
    tt_ok = "TEAMTAILOR_API_KEY" in st.secrets
except Exception:
    tt_ok = False
if not tt_ok:
    st.error("Falta `TEAMTAILOR_API_KEY` en los secrets. Agrégala para usar este módulo.")
    st.stop()
API_KEY = st.secrets["TEAMTAILOR_API_KEY"]

# ---------------------------------------------------------------------------
# Paso 1 — Elegir la vacante
# ---------------------------------------------------------------------------
st.subheader("1 · Elige la vacante")

col_a, col_b = st.columns([3, 2])
with col_a:
    if st.button("🔄 Cargar vacantes (activas + unlisted)", use_container_width=True):
        try:
            with st.spinner("Consultando Teamtailor..."):
                st.session_state.tt_vacantes = tt.listar_vacantes(API_KEY)
        except tt.TeamtailorError as e:
            st.error(str(e))

vacantes = st.session_state.get("tt_vacantes") or []
seleccion = None
if vacantes:
    opciones = {f"{v['titulo']}  ·  {v['status']}  ·  ID {v['id']}": v for v in vacantes}
    elegido = st.selectbox("Vacante", list(opciones.keys()), index=None,
                           placeholder="Busca por nombre de la vacante...")
    if elegido:
        seleccion = opciones[elegido]

with col_b:
    id_manual = st.text_input("...o pega el ID de la vacante", placeholder="ej. 7130357")
    if id_manual.strip():
        if st.button("Validar ID", use_container_width=True):
            try:
                st.session_state.tt_vacante_manual = tt.obtener_vacante(API_KEY, id_manual.strip())
            except tt.TeamtailorError as e:
                st.error(str(e))
        if st.session_state.get("tt_vacante_manual", {}).get("id") == id_manual.strip():
            seleccion = st.session_state.tt_vacante_manual

if seleccion:
    st.success(f"Vacante elegida: **{seleccion['titulo']}** ({seleccion['status']}) — ID {seleccion['id']}")

# ---------------------------------------------------------------------------
# Paso 2 — Subir el CSV
# ---------------------------------------------------------------------------
st.subheader("2 · Sube el CSV de candidatos")
st.caption(
    "Sirve el CSV del extractor (columnas Nombre / Email / Teléfono / LinkedIn / Titular) "
    "o cualquier CSV con columnas parecidas. El titular se guarda como nota (pitch)."
)
archivo = st.file_uploader("CSV de candidatos", type=["csv"], label_visibility="collapsed")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return s.strip().lower()


def _detectar(cols: list, *aliases: str):
    normadas = {_norm(c): c for c in cols}
    for a in aliases:
        for n, original in normadas.items():
            if a in n:
                return original
    return None


filas_tt = []
if archivo is not None:
    texto = archivo.getvalue().decode("utf-8-sig", errors="replace")
    lector = csv.DictReader(io.StringIO(texto))
    cols = lector.fieldnames or []
    c_nombre = _detectar(cols, "nombre", "name", "candidato")
    c_email = _detectar(cols, "email", "correo", "mail")
    c_tel = _detectar(cols, "telefono", "phone", "celular")
    c_url = _detectar(cols, "linkedin", "url", "perfil")
    c_pitch = _detectar(cols, "titular", "headline", "cargo actual", "current role")

    if not c_nombre:
        st.error("No encontré una columna de nombre en el CSV (busqué 'Nombre', 'Name', 'Candidato').")
    else:
        for fila in lector:
            nombre = (fila.get(c_nombre) or "").strip()
            if not nombre:
                continue
            partes = nombre.split()
            email = (fila.get(c_email) or "").strip() if c_email else ""
            if email in ("—", "-"):
                email = ""
            filas_tt.append({
                "first-name": partes[0],
                "last-name": " ".join(partes[1:]) or "-",
                "email": email,
                "phone": (fila.get(c_tel) or "").strip() if c_tel else "",
                "linkedin-url": (fila.get(c_url) or "").strip() if c_url else "",
                "pitch": (fila.get(c_pitch) or "").strip()[:280] if c_pitch else "",
                "tags": ["prometeo"],
            })
        con_email = sum(1 for f in filas_tt if f["email"])
        st.info(
            f"Detecté **{len(filas_tt)} candidatos** "
            f"(columnas: nombre=`{c_nombre}`, email=`{c_email}`, teléfono=`{c_tel}`, "
            f"linkedin=`{c_url}`, nota=`{c_pitch}`). Con email: {con_email} — "
            "los que tienen email se deduplican (si ya existen en Teamtailor no se crean doble)."
        )
        st.dataframe(
            [{"Nombre": f"{f['first-name']} {f['last-name']}", "Email": f["email"] or "—",
              "LinkedIn": f["linkedin-url"] or "—"} for f in filas_tt[:5]],
            use_container_width=True, hide_index=True,
        )
        if len(filas_tt) > 5:
            st.caption(f"...y {len(filas_tt) - 5} más.")

# ---------------------------------------------------------------------------
# Paso 3 — Confirmar y enviar
# ---------------------------------------------------------------------------
st.subheader("3 · Enviar")
if not seleccion or not filas_tt:
    st.caption("Elige una vacante y sube un CSV para habilitar el envío.")
else:
    st.warning(
        f"Vas a crear/asociar **{len(filas_tt)} candidatos reales** en la vacante "
        f"**{seleccion['titulo']}** de tu Teamtailor. Tu equipo los verá en el pipeline."
    )
    seguro = st.checkbox("Entiendo que esto escribe candidatos reales en Teamtailor.")
    if st.button(
        f"📤 Enviar {len(filas_tt)} candidato(s) a: {seleccion['titulo']}",
        type="primary", use_container_width=True,
        disabled=not seguro or st.session_state.get("tt_enviando", False),
    ):
        st.session_state.tt_enviando = True
        try:
            barra = st.progress(0.0, text="Enviando candidatos...")
            resumen = tt.enviar_candidatos(
                API_KEY, seleccion["id"], filas_tt,
                on_progress=lambda h, t: barra.progress(h / t, text=f"Enviando... {h}/{t}"),
            )
            barra.progress(1.0, text="¡Listo!")
            st.session_state.tt_resultado = resumen
            st.balloons()
        finally:
            st.session_state.tt_enviando = False

resultado = st.session_state.get("tt_resultado")
if resultado:
    st.divider()
    col_img, col_datos = st.columns([1, 2.2], vertical_alignment="center")
    with col_img:
        if ASTRONAUTA.exists():
            st.image(str(ASTRONAUTA), use_container_width=True)
    with col_datos:
        st.write("### 🚀 Misión cumplida")
        st.caption("Los candidatos ya están en el pipeline de la vacante en Teamtailor.")
        m1, m2, m3 = st.columns(3)
        m1.metric("✅ Creados", len(resultado["creados"]))
        m2.metric("♻️ Ya existían", len(resultado["existentes"]))
        m3.metric("⚠️ Errores", len(resultado["errores"]))
    if resultado["existentes"]:
        st.caption("Los que ya existían no se duplicaron: solo se asociaron a la vacante.")
    if resultado["errores"]:
        st.error(f"⚠️ {len(resultado['errores'])} candidato(s) con error.")
        st.download_button(
            "⬇️ Descargar detalle de errores",
            data="\n".join(resultado["errores"]),
            file_name="errores_teamtailor.txt", mime="text/plain",
        )
