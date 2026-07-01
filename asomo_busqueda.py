"""
Asomo: replica la búsqueda de Sales Navigator en harvestapi y lee el tamaño del pool.
Modo Short (barato) — solo para comparar cuántos candidatos hay (totalElements).
"""
import json, sys, tomllib, urllib.request, urllib.error
from pathlib import Path

SECRETS = Path(__file__).parent / ".streamlit" / "secrets.toml"
ENDPOINT = "https://api.apify.com/v2/acts/harvestapi~linkedin-profile-search/run-sync-get-dataset-items"

BOOLEAN = ('("backup" OR "Cohesity" OR "Commvault" OR "Veeam" OR "Veritas") '
           'AND ("infrastructure" OR "storage" OR "backup administrator" OR "support engineer")')

ENTRADA = {
    "profileScraperMode": "Short",          # barato: solo para contar
    "searchQuery": BOOLEAN,
    "locations": ["India", "Philippines"],
    "yearsOfExperienceIds": ["4"],          # 6-10 años (igual que Sales Nav)
    "functionIds": ["13"],                  # Information Technology (aprox. industria tech)
    "maxItems": 25,
}

tok = tomllib.load(open(SECRETS, "rb"))["APIFY_TOKEN"]
body = json.dumps(ENTRADA).encode("utf-8")
req = urllib.request.Request(f"{ENDPOINT}?token={tok}", data=body, method="POST",
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        items = json.loads(r.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    sys.exit(f"ERROR HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}")

items = [x for x in items if "error" not in x]
print("Perfiles en esta página:", len(items))
if items:
    meta = items[0].get("_meta", {}).get("pagination", {})
    print("POOL TOTAL (totalElements):", meta.get("totalElements"))
    print("Páginas totales:", meta.get("totalPages"))
    print("\nMuestra de los primeros:")
    for p in items[:6]:
        nombre = (p.get("firstName", "") + " " + p.get("lastName", "")).strip()
        print(f"  - {nombre[:24]:<24} | {(p.get('headline') or '')[:55]}")
else:
    print("Sin resultados (revisar filtros).")
