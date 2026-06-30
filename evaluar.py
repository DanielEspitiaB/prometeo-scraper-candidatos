"""
Evaluador determinista — Prometeo (zona determinista).

Flujo:
  1. Lee perfiles crudos de Apify desde salida_validacion.json.
  2. Arma el "perfil limpio" (solo los campos que el modelo necesita).
  3. Evalua cada perfil con Claude contra un scorecard (plantilla de prompt FIJA).
  4. El codigo (no el modelo) suma puntos y calcula la banda con scorecard.py.
  5. Escribe un Excel con formato: resultados ordenados por puntaje.

Reglas que respeta:
  - ANTHROPIC_API_KEY se LEE de .streamlit/secrets.toml, nunca va en el codigo.
  - La llamada a Claude usa un cuerpo FIJO; el codigo inyecta los datos (no un agente).
  - Claude SOLO asigna puntos + justificacion por criterio. La suma total y la
    banda las calcula el codigo (determinista), incluida la regla de eliminatorios.

Como correr (desde la carpeta "Scrapper Candidatos"):
    python evaluar.py
"""

import json
import re
import sys
import tomllib
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import asdict

import scorecard as sc

CARPETA = Path(__file__).parent
SECRETS = CARPETA / ".streamlit" / "secrets.toml"
ENTRADA = CARPETA / "salida_validacion.json"
SALIDA = CARPETA / "resultados_evaluacion.xlsx"

MODELO = "claude-sonnet-4-6"  # modelo por defecto: prioriza calidad de evaluacion (no perder buenos candidatos)
ENDPOINT_CLAUDE = "https://api.anthropic.com/v1/messages"

# Precios aproximados en USD por millon de tokens (entrada / salida)
PRECIOS_USD = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


def costo_usd(modelo: str, usage: dict) -> float:
    pin, pout = PRECIOS_USD.get(modelo, (3.0, 15.0))
    return (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout) / 1_000_000

# Apify: actor de enriquecimiento de perfiles (mismo que validamos)
APIFY_ACTOR = "dev_fusion~linkedin-profile-scraper"
APIFY_ENDPOINT = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"

# Colores por banda para el Excel (formato ARGB de openpyxl)
COLORES_BANDA = {
    "Ideal": "C6EFCE",          # verde
    "Avanzar": "D9EAD3",        # verde claro
    "Pendiente": "FFEB9C",      # amarillo
    "No recomendado": "FFC7CE", # rojo
}


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
def leer_api_key() -> str:
    if not SECRETS.exists():
        sys.exit(f"No encuentro el archivo de secrets en: {SECRETS}")
    data = tomllib.load(open(SECRETS, "rb"))
    key = data.get("ANTHROPIC_API_KEY", "")
    if not key or key.startswith("PEGA_AQUI"):
        sys.exit("Falta tu ANTHROPIC_API_KEY en .streamlit/secrets.toml.")
    return key


# ---------------------------------------------------------------------------
# Perfil limpio: de ~70 campos crudos a solo lo que el modelo necesita
# ---------------------------------------------------------------------------
def perfil_limpio(p: dict) -> dict:
    return {
        "nombre": p.get("fullName"),
        "titular": p.get("headline"),
        "resumen": (p.get("about") or "")[:600],
        "ubicacion": p.get("addressWithCountry"),
        "anios_experiencia_total": p.get("totalExperienceYears"),
        "cargo_actual": p.get("jobTitle"),
        "experiencias": [
            {
                "cargo": e.get("title"),
                "empresa": e.get("companyName"),
                "industria": e.get("companyIndustry"),
                "desde": e.get("jobStartedOn"),
                "hasta": e.get("jobEndedOn"),
                "sigue_ahi": e.get("jobStillWorking"),
                "descripcion": (e.get("jobDescription") or "")[:400],
            }
            for e in (p.get("experiences") or [])
        ],
        "educacion": [
            {"institucion": e.get("title"), "titulo": e.get("subtitle")}
            for e in (p.get("educations") or [])
        ],
        "skills": [s.get("title") if isinstance(s, dict) else s for s in (p.get("skills") or [])],
    }


def datos_contacto(p: dict) -> dict:
    """Datos que van al Excel para el reclutador (NO al modelo)."""
    return {
        "email": p.get("email") or "",
        "telefono": p.get("mobileNumber") or "",
        "url": p.get("linkedinUrl") or p.get("linkedinPublicUrl") or "",
    }


# ---------------------------------------------------------------------------
# Raspado de perfiles por URL (Apify) — cuerpo de peticion FIJO
# ---------------------------------------------------------------------------
def scrape_perfiles(urls: list, apify_token: str) -> list:
    """Enriquece una lista de URLs de LinkedIn con dev_fusion. Body fijo: {profileUrls: [...]}."""
    body = json.dumps({"profileUrls": list(urls)}).encode("utf-8")
    req = urllib.request.Request(
        f"{APIFY_ENDPOINT}?token={apify_token}", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        items = json.loads(resp.read().decode("utf-8"))
    buenos = [it for it in items if "error" not in it]
    if not buenos and items:
        raise RuntimeError(items[0].get("error", "Apify devolvio un error desconocido."))
    return buenos


# ---------------------------------------------------------------------------
# Prompt FIJO para Claude
# ---------------------------------------------------------------------------
def construir_prompt(scorecard: sc.Scorecard, perfil: dict) -> str:
    criterios = [
        {"id": c.id, "criterio": c.label, "tipo": c.type,
         "puntos_maximos": c.points, "nota": c.notes}
        for c in scorecard.criteria
    ]
    return (
        "Eres un evaluador experto de talento para una consultora de headhunting. "
        "Recibes un SCORECARD con criterios y un PERFIL de LinkedIn ya resumido.\n\n"
        "Tu tarea: para CADA criterio, decide cuantos puntos merece el candidato "
        "(entre 0 y 'puntos_maximos'), basandote en la evidencia del perfil "
        "(titular, resumen, experiencias, skills, educacion). Sé estricto y justo.\n\n"
        "Reglas:\n"
        "- Para criterios de tipo 'eliminatory': si el candidato NO cumple el requisito, "
        "pon \"cumple\": false (eso lo descalifica). Si cumple, \"cumple\": true.\n"
        "- Para tipo 'scored': \"cumple\" es informativo; lo importante son los puntos.\n"
        "- Si no hay evidencia suficiente de un criterio, otorga pocos o cero puntos.\n"
        "- La justificacion debe ser UNA frase corta citando la evidencia concreta.\n\n"
        "Responde UNICAMENTE con JSON valido, sin texto extra ni markdown, con esta forma exacta:\n"
        '{"criterios": [{"id": "...", "puntos": 0, "cumple": true, "justificacion": "..."}]}\n\n'
        f"SCORECARD (rol: {scorecard.role}, ubicacion buscada: {scorecard.location}):\n"
        f"{json.dumps(criterios, ensure_ascii=False, indent=2)}\n\n"
        f"PERFIL DEL CANDIDATO:\n{json.dumps(perfil, ensure_ascii=False, indent=2)}"
    )


def llamar_claude(prompt: str, api_key: str, modelo: str = MODELO):
    body = json.dumps({
        "model": modelo,
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT_CLAUDE, data=body, method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"Claude respondio error HTTP {e.code}:\n{e.read().decode('utf-8', 'replace')}")
    texto = data["content"][0]["text"]
    usage = data.get("usage", {})
    # Extraer el bloque JSON de forma robusta
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if not m:
        raise ValueError(f"Claude no devolvio JSON:\n{texto}")
    return json.loads(m.group(0)), usage


# ---------------------------------------------------------------------------
# Evaluacion + banda (el codigo hace las cuentas, no el modelo)
# ---------------------------------------------------------------------------
def evaluar_perfil(scorecard: sc.Scorecard, crudo: dict, api_key: str, modelo: str = MODELO) -> dict:
    limpio = perfil_limpio(crudo)
    respuesta, usage = llamar_claude(construir_prompt(scorecard, limpio), api_key, modelo)

    por_id = {c.id: c for c in scorecard.criteria}
    puntos = {}
    justificaciones = []
    descalificado = False

    for item in respuesta.get("criterios", []):
        cid = item.get("id")
        crit = por_id.get(cid)
        if not crit:
            continue
        p = max(0, min(int(item.get("puntos", 0)), crit.points))  # nunca supera el maximo
        puntos[cid] = p
        if crit.type == "eliminatory" and item.get("cumple") is False:
            descalificado = True
        justificaciones.append(f"[{crit.label}] {item.get('justificacion', '')}")

    total = sum(puntos.values())
    banda = scorecard.band_for(total, disqualified=descalificado)
    return {
        "nombre": limpio["nombre"],
        "puntos": puntos,
        "total": total,
        "descalificado": descalificado,
        "banda": banda,
        "justificacion": "  •  ".join(justificaciones),
        "contacto": datos_contacto(crudo),
        "usage": usage,
        "modelo": modelo,
    }


# ---------------------------------------------------------------------------
# Excel con formato
# ---------------------------------------------------------------------------
def construir_workbook(scorecard: sc.Scorecard, resultados: list):
    """Construye el libro de Excel en memoria (lo usa tanto el script como la app)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"

    criterios = scorecard.criteria
    encabezados = ["Candidato", "Banda", "Puntaje total"] + \
        [c.label for c in criterios] + ["Justificación", "Email", "Teléfono", "LinkedIn"]
    ws.append(encabezados)
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="404040")
        celda.alignment = Alignment(vertical="center", wrap_text=True)

    # Ordenar de mejor a peor puntaje
    for r in sorted(resultados, key=lambda x: x["total"], reverse=True):
        fila = [r["nombre"], r["banda"], r["total"]] + \
            [r["puntos"].get(c.id, 0) for c in criterios] + \
            [r["justificacion"], r["contacto"]["email"], r["contacto"]["telefono"], r["contacto"]["url"]]
        ws.append(fila)
        celda_banda = ws.cell(row=ws.max_row, column=2)
        color = COLORES_BANDA.get(r["banda"])
        if color:
            celda_banda.fill = PatternFill("solid", fgColor=color)
            celda_banda.font = Font(bold=True)

    # Anchos de columna basicos
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 12
    return wb


def escribir_excel(scorecard: sc.Scorecard, resultados: list):
    """Guarda el Excel en disco (para el script standalone)."""
    construir_workbook(scorecard, resultados).save(SALIDA)


def construir_workbook_datos(crudos: list):
    """Excel con los DATOS de cada candidato (sin evaluacion). Branding Prometeo (navy)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = "Candidatos"
    encabezados = ["Nombre", "Titular", "Ubicación", "Años exp.", "Cargo actual",
                   "Empresa actual", "Email", "Teléfono", "LinkedIn",
                   "Skills", "Educación", "Experiencia"]
    ws.append(encabezados)
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="142649")  # azul marino Prometeo
        celda.alignment = Alignment(vertical="center", wrap_text=True)

    for crudo in crudos:
        p = perfil_limpio(crudo)
        c = datos_contacto(crudo)
        exps = p["experiencias"]
        empresa_actual = next((e.get("empresa") for e in exps if e.get("sigue_ahi") and e.get("empresa")), "")
        if not empresa_actual and exps:
            empresa_actual = exps[0].get("empresa") or ""
        skills = ", ".join(str(s) for s in p["skills"])
        educacion = " | ".join(
            f"{e['institucion']} ({e['titulo']})" if e.get("titulo") else (e.get("institucion") or "")
            for e in p["educacion"] if e.get("institucion")
        )
        experiencia = " | ".join(
            f"{e['cargo']} @ {e['empresa'] or '?'} ({e['desde'] or '?'}–{e['hasta'] or 'actual'})"
            for e in exps if e.get("cargo")
        )
        ws.append([
            p["nombre"], p["titular"], p["ubicacion"], p["anios_experiencia_total"],
            p["cargo_actual"], empresa_actual, c["email"], c["telefono"], c["url"],
            skills, educacion, experiencia,
        ])

    anchos = {"A": 22, "B": 42, "C": 22, "D": 9, "E": 24, "F": 24,
              "G": 26, "H": 16, "I": 38, "J": 40, "K": 40, "L": 60}
    for col, w in anchos.items():
        ws.column_dimensions[col].width = w
    return wb


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------
def main():
    api_key = leer_api_key()
    if not ENTRADA.exists():
        sys.exit(f"No encuentro {ENTRADA.name}. Corre primero validar_apify.py.")
    crudos = json.load(open(ENTRADA, encoding="utf-8"))
    crudos = [c for c in crudos if "error" not in c]  # ignora respuestas de error

    scorecard = sc.senior_go_developer()  # scorecard de prueba
    print(f"Evaluando {len(crudos)} perfil(es) contra: {scorecard.role}\n")

    resultados = []
    for crudo in crudos:
        print(f"  Evaluando: {crudo.get('fullName')} ...")
        resultados.append(evaluar_perfil(scorecard, crudo, api_key))

    print("\n" + "=" * 60)
    print("RESULTADOS (de mayor a menor puntaje):")
    print("=" * 60)
    for r in sorted(resultados, key=lambda x: x["total"], reverse=True):
        marca = "  [DESCALIFICADO]" if r["descalificado"] else ""
        print(f"  {r['nombre']:<24} {r['total']:>3} pts  -> {r['banda']}{marca}")

    escribir_excel(scorecard, resultados)
    print("\nExcel generado:", SALIDA.name)


if __name__ == "__main__":
    main()
