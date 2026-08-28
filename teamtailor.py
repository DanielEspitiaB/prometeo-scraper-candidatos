"""
Cliente mínimo de la API de Teamtailor (cuenta EU).

Reglas del proyecto:
  - La API key se LEE de secrets (nunca va en el código).
  - Peticiones HTTP fijas y directas (formato JSON:API de Teamtailor).
  - Escribir en el ATS es serio: cada función hace UNA cosa clara y
    la app pide confirmación explícita antes de enviar.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.teamtailor.com/v1"  # servidores de Europa (cuenta @eu)
API_VERSION = "20240404"


class TeamtailorError(RuntimeError):
    pass


def _pedir(metodo: str, url: str, api_key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=metodo, headers={
        "Authorization": f"Token token={api_key}",
        "X-Api-Version": API_VERSION,
        "Content-Type": "application/vnd.api+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:400]
        raise TeamtailorError(f"Teamtailor respondió HTTP {e.code}: {detalle}") from e
    except urllib.error.URLError as e:
        raise TeamtailorError(f"No pude conectar con Teamtailor: {e.reason}") from e


def _get(path: str, api_key: str, params: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return _pedir("GET", url, api_key)


# ---------------------------------------------------------------------------
# Vacantes
# ---------------------------------------------------------------------------
def listar_vacantes(api_key: str) -> list:
    """Vacantes publicadas (activas) y unlisted, con paginación. Solo lectura."""
    vacantes, vistos = [], set()
    for status in ("published", "unlisted"):
        pagina = _get("/jobs", api_key, {"filter[status]": status, "page[size]": "30"})
        while True:
            for j in pagina.get("data", []):
                jid = str(j.get("id"))
                if jid in vistos:
                    continue
                vistos.add(jid)
                at = j.get("attributes", {})
                vacantes.append({
                    "id": jid,
                    "titulo": at.get("title") or "(sin título)",
                    "status": at.get("human-status") or status,
                })
            siguiente = (pagina.get("links") or {}).get("next")
            if not siguiente:
                break
            pagina = _pedir("GET", siguiente, api_key)
    return vacantes


def obtener_vacante(api_key: str, job_id: str) -> dict:
    """Trae una vacante puntual por ID (para validar un ID pegado a mano)."""
    data = _get(f"/jobs/{job_id}", api_key)
    at = (data.get("data") or {}).get("attributes", {})
    return {"id": str(job_id), "titulo": at.get("title") or "(sin título)",
            "status": at.get("human-status") or "?"}


# ---------------------------------------------------------------------------
# Candidatos
# ---------------------------------------------------------------------------
def buscar_candidato_por_email(api_key: str, email: str):
    """Devuelve el id del candidato si ya existe ese email, o None."""
    if not email:
        return None
    data = _get("/candidates", api_key, {"filter[email]": email, "page[size]": "1"})
    items = data.get("data") or []
    return str(items[0]["id"]) if items else None


def crear_candidato(api_key: str, atributos: dict) -> str:
    """Crea un candidato. atributos usa las claves de Teamtailor (first-name, email...)."""
    limpios = {k: v for k, v in atributos.items() if v}
    body = {"data": {"type": "candidates", "attributes": limpios}}
    data = _pedir("POST", f"{BASE}/candidates", api_key, body)
    return str(data["data"]["id"])


def asociar_a_vacante(api_key: str, candidato_id: str, job_id: str) -> str:
    """Crea la aplicación del candidato a la vacante (aparece en el pipeline del job)."""
    body = {"data": {
        "type": "job-applications",
        "attributes": {"sourced": True},  # sourced: lo agregó el reclutador, no aplicó solo
        "relationships": {
            "candidate": {"data": {"type": "candidates", "id": str(candidato_id)}},
            "job": {"data": {"type": "jobs", "id": str(job_id)}},
        },
    }}
    data = _pedir("POST", f"{BASE}/job-applications", api_key, body)
    return str(data["data"]["id"])


# ---------------------------------------------------------------------------
# Envío de un lote de candidatos (con dedupe por email y ritmo suave)
# ---------------------------------------------------------------------------
def enviar_candidatos(api_key: str, job_id: str, filas: list, on_progress=None) -> dict:
    """Envía candidatos a una vacante. filas = [{first-name, last-name, email, phone,
    linkedin-url, pitch, tags}, ...]. Devuelve resumen {creados, existentes, errores}.
    """
    creados, existentes, errores = [], [], []
    for i, fila in enumerate(filas, 1):
        nombre = f"{fila.get('first-name', '')} {fila.get('last-name', '')}".strip()
        try:
            cid = buscar_candidato_por_email(api_key, fila.get("email"))
            if cid:
                existentes.append(nombre)
            else:
                cid = crear_candidato(api_key, fila)
                creados.append(nombre)
            asociar_a_vacante(api_key, cid, job_id)
        except TeamtailorError as e:
            errores.append(f"{nombre or '(sin nombre)'}: {e}")
        if on_progress:
            on_progress(i, len(filas))
        time.sleep(0.25)  # ritmo suave: bajo el límite de peticiones de Teamtailor
    return {"creados": creados, "existentes": existentes, "errores": errores}
