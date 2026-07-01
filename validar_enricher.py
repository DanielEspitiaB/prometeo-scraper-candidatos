"""
Valida el enricher barato: harvestapi/linkedin-profile-scraper (modo SIN email, $0.004).
Enriquece los 3 perfiles de siempre y compara la completitud vs dev_fusion.
"""
import json, sys, tomllib, urllib.request, urllib.error
from pathlib import Path

CARPETA = Path(__file__).parent
SECRETS = CARPETA / ".streamlit" / "secrets.toml"
ENDPOINT = "https://api.apify.com/v2/acts/harvestapi~linkedin-profile-scraper/run-sync-get-dataset-items"

URLS = [
    "https://www.linkedin.com/in/sergiojunco/",
    "https://www.linkedin.com/in/jonatanpasqualino/",
    "https://www.linkedin.com/in/pablo-javier-panzardi-3793b214/",
]
ENTRADA = {"profileScraperMode": "Profile details no email ($4 per 1k)", "urls": URLS}

tok = tomllib.load(open(SECRETS, "rb"))["APIFY_TOKEN"]
body = json.dumps(ENTRADA).encode("utf-8")
req = urllib.request.Request(f"{ENDPOINT}?token={tok}", data=body, method="POST",
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        items = json.loads(r.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    sys.exit(f"ERROR HTTP {e.code}: {e.read().decode('utf-8','replace')[:500]}")

items = [x for x in items if "error" not in x]
(CARPETA / "enricher_validacion.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"harvestapi devolvió {len(items)} perfil(es)\n")

for p in items:
    nombre = (p.get("firstName", "") + " " + p.get("lastName", "")).strip()
    exp = p.get("experience") or []
    con_desc = sum(1 for e in exp if (e.get("description") or "").strip())
    edu = p.get("education") or []
    skills = p.get("skills") or []
    certs = p.get("certifications") or []
    langs = p.get("languages") or []
    emails = p.get("emails") or []
    print(f"=== {nombre} ===")
    print(f"  headline: {(p.get('headline') or '')[:60]}")
    print(f"  experiencias: {len(exp)} (con descripción de tareas: {con_desc})")
    print(f"  skills: {len(skills)} | educación: {len(edu)} | certs: {len(certs)} | idiomas: {len(langs)}")
    print(f"  emails (debe venir vacío en modo sin-email): {emails}")
    print()
