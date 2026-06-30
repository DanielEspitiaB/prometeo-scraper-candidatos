"""
Prueba de validacion — scraper dev_fusion/linkedin-profile-scraper (Apify).

OBJETIVO (Fase 0): traer 2-3 perfiles reales y ver que campos llegan,
para decidir juntos si la calidad de datos sirve para evaluar candidatos.
Esto NO es el pipeline: es solo una prueba puntual y controlada.

Reglas que respeta este script:
  - La llave (APIFY_TOKEN) se LEE desde .streamlit/secrets.toml, nunca va en el codigo.
  - El cuerpo de la peticion es FIJO y directo (no se arma dinamicamente).
  - Solo lee datos; no toca ningun otro archivo del proyecto.

Como correr (desde la carpeta "Scrapper Candidatos"):
    python validar_apify.py
"""

import json
import sys
import tomllib
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# 1) Configuracion fija de la prueba
# ---------------------------------------------------------------------------
ACTOR = "dev_fusion~linkedin-profile-scraper"  # id del actor en Apify (~ separa usuario/actor)
ENDPOINT = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"

# Los 3 perfiles reales de la prueba. Cuerpo de peticion FIJO (Regla #2).
PERFILES = [
    "https://www.linkedin.com/in/sergiojunco/",
    "https://www.linkedin.com/in/jonatanpasqualino/",
    "https://www.linkedin.com/in/pablo-javier-panzardi-3793b214/",
]
BODY = {"profileUrls": PERFILES}

SECRETS = Path(__file__).parent / ".streamlit" / "secrets.toml"
SALIDA = Path(__file__).parent / "salida_validacion.json"


# ---------------------------------------------------------------------------
# 2) Leer el token desde el archivo de secrets (nunca escrito en el codigo)
# ---------------------------------------------------------------------------
def leer_token() -> str:
    if not SECRETS.exists():
        sys.exit(f"No encuentro el archivo de secrets en: {SECRETS}")
    with open(SECRETS, "rb") as f:
        data = tomllib.load(f)
    token = data.get("APIFY_TOKEN", "")
    if not token or token.startswith("PEGA_AQUI"):
        sys.exit(
            "Todavia no pegaste tu token real en .streamlit/secrets.toml.\n"
            "Abre ese archivo, reemplaza PEGA_AQUI_TU_TOKEN_DE_APIFY por tu token, y vuelve a correr."
        )
    return token


# ---------------------------------------------------------------------------
# 3) Llamar a Apify con una peticion HTTP fija y directa
# ---------------------------------------------------------------------------
def llamar_apify(token: str) -> list:
    url = f"{ENDPOINT}?token={token}"
    datos = json.dumps(BODY).encode("utf-8")
    req = urllib.request.Request(
        url, data=datos, headers={"Content-Type": "application/json"}, method="POST"
    )
    print("Llamando a Apify... (esto puede tardar 1-2 minutos mientras raspa los perfiles)\n")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", errors="replace")
        sys.exit(f"Apify respondio con error HTTP {e.code}:\n{cuerpo}")
    except urllib.error.URLError as e:
        sys.exit(f"No me pude conectar a Apify: {e.reason}")


# ---------------------------------------------------------------------------
# 4) Mostrar un resumen legible de cada perfil
# ---------------------------------------------------------------------------
def buscar_jobdescription_vacio(item: dict) -> str:
    """Confirma la limitacion conocida: jobDescription suele venir vacio."""
    encontrados, con_texto = 0, 0
    for exp in item.get("experiences", []) or item.get("positions", []) or []:
        if isinstance(exp, dict) and "jobDescription" in exp:
            encontrados += 1
            if (exp.get("jobDescription") or "").strip():
                con_texto += 1
    if encontrados == 0:
        return "no aparece el campo jobDescription en las experiencias"
    return f"{con_texto} de {encontrados} experiencias traen texto en jobDescription"


def resumir(items: list):
    print("=" * 70)
    print(f"Apify devolvio {len(items)} perfil(es).")
    print("=" * 70)

    for i, item in enumerate(items, 1):
        print(f"\n----- PERFIL {i} -----")
        # Campos clave que mencionaste. Usamos varios nombres posibles por si acaso.
        nombre = item.get("fullName") or item.get("name") or "(sin nombre)"
        anios = item.get("totalExperienceYears") or item.get("experienceYears") or "?"
        url_pub = item.get("linkedinUrl") or item.get("publicUrl") or item.get("url") or "?"
        skills = item.get("skills") or []
        idiomas = item.get("languages") or []

        print(f"  Nombre:            {nombre}")
        print(f"  Años experiencia:  {anios}")
        print(f"  URL publica:       {url_pub}")
        print(f"  # de skills:       {len(skills)}", end="")
        if skills:
            muestra = [s if isinstance(s, str) else s.get('name', s) for s in skills[:8]]
            print(f"   ej: {', '.join(map(str, muestra))}")
        else:
            print()
        print(f"  Idiomas:           ", end="")
        if idiomas:
            print(", ".join(
                f"{l.get('name', l)} ({l.get('proficiency', '?')})" if isinstance(l, dict) else str(l)
                for l in idiomas
            ))
        else:
            print("(ninguno)")
        print(f"  jobDescription:    {buscar_jobdescription_vacio(item)}")

        # Lista TODOS los campos disponibles, para revisar juntos que mas llega.
        print(f"  Campos disponibles: {', '.join(sorted(item.keys()))}")


# ---------------------------------------------------------------------------
# 5) Flujo principal
# ---------------------------------------------------------------------------
def main():
    token = leer_token()
    items = llamar_apify(token)
    SALIDA.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    resumir(items)
    print("\n" + "=" * 70)
    print(f"Respuesta cruda completa guardada en: {SALIDA.name}")
    print("Revisa ese archivo si quieres ver TODOS los datos de cada perfil.")
    print("=" * 70)


if __name__ == "__main__":
    main()
