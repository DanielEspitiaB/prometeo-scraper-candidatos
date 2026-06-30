# Prometeo MVP — Zona conversacional (Streamlit)

Esqueleto del chat que construye el scorecard, lo confirma y lo bloquea como JSON oculto.
Corre **sin API keys**.

## Correr localmente

```bash
cd prometeo-mvp
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Abre `http://localhost:8501`. Prueba el boton **Cargar plantilla: Senior Go Developer**
para ver el flujo completo: construir → confirmar → bloquear.

## Arquitectura — dos zonas

```
Zona conversacional  (este repo)        Zona determinista  (siguiente paso)
ChatUI Streamlit                        Backend Python
  -> ScoreCardBuilder                     -> Apify (busqueda + perfil)
  -> Scorecard JSON (oculto, bloqueado) --> Evaluador Claude
                                          -> Excel (4 pestanias)
```

`scorecard.py` es el **contrato** compartido. El reclutador nunca ve el JSON.
No hay AI tool-calling en el backend: las llamadas a Apify y Claude usaran
HTTP Request fijos.

## Siguientes pasos

1. **Claude en el builder**: el reclutador describe el rol en prosa y Claude propone
   los criterios automaticamente (reemplaza la captura manual). Llamada HTTP directa a
   `api.anthropic.com/v1/messages`, key desde secrets.
2. **Backend determinista**: input de URLs/filtros, cliente Apify, evaluador, generador Excel.
3. **Deploy**: push a GitHub -> Streamlit Community Cloud. Secrets en el gestor de Streamlit.

## Pendiente de Fase 0 (antes de cablear el backend)

- Validar `harvestapi/linkedin-profile-search` sobre perfiles colombianos reales.
- Confirmar el esquema de entrada/salida de ese actor para definir el JSON de filtros.
