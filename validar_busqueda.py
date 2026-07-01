"""
Validación del scraper de BÚSQUEDA: harvestapi/linkedin-profile-search.

Corre 2 búsquedas de prueba (Filipinas + India) para la vacante Support Engineer
de P1, y reporta: cuántos vienen, cuántos con >=6 años, y qué campos trae.

Reglas: token leído de secrets, cuerpo de petición FIJO, solo es una prueba.
"""

import json
import sys
import tomllib
import urllib.request
import urllib.error
from pathlib import Path

CARPETA = Path(__file__).parent
SECRETS = CARPETA / ".streamlit" / "secrets.toml"
SALIDA = CARPETA / "busqueda_validacion.json"

ACTOR = "harvestapi~linkedin-profile-search"
ENDPOINT = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"

CARGOS = [
    "Senior Support Engineer", "Senior System Administrator", "Backup Administrator",
    "Senior Backup Engineer", "L3 Support Engineer", "Infrastructure Engineer",
]

BUSQUEDAS = [
    ("Filipinas", {
        "profileScraperMode": "Full",
        "searchQuery": "backup recovery data protection VMware",
        "currentJobTitles": CARGOS,
        "locations": ["Philippines"],
        "maxItems": 25,
    }),
    ("India", {
        "profileScraperMode": "Full",
        "searchQuery": "backup recovery data protection VMware",
        "currentJobTitles": CARGOS,
        "locations": ["India"],
        "maxItems": 25,
    }),
]


def token():
    data = tomllib.load(open(SECRETS, "rb"))
    t = data.get("APIFY_TOKEN", "")
    if not t or t.startswith("PEGA_AQUI"):
        sys.exit("Falta APIFY_TOKEN en .streamlit/secrets.toml")
    return t


def correr(entrada, tok):
    body = json.dumps(entrada).encode("utf-8")
    req = urllib.request.Request(
        f"{ENDPOINT}?token={tok}", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")
        print(f"  ERROR HTTP {e.code}: {cuerpo[:400]}")
        return []


def anios(p):
    """Intenta sacar los años de experiencia probando varios nombres de campo."""
    for k in ("totalExperienceYears", "experienceYears", "yearsOfExperience"):
        v = p.get(k)
        if isinstance(v, (int, float)):
            return v
    return None


def main():
    tok = token()
    todo = {}
    for pais, entrada in BUSQUEDAS:
        print(f"\n=== Buscando en {pais} ... ===")
        items = correr(entrada, tok)
        items = [x for x in items if "error" not in x] if items else []
        print(f"  Devueltos: {len(items)}")
        todo[pais] = items
        if items:
            p0 = items[0]
            print(f"  Campos disponibles (primer perfil): {', '.join(sorted(p0.keys()))[:400]}")

    SALIDA.write_text(json.dumps(todo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRespuesta cruda guardada en: {SALIDA.name}")


if __name__ == "__main__":
    main()
