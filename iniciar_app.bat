@echo off
REM ============================================================
REM  Prometeo Talent - Extractor de candidatos
REM  Doble clic en este archivo para abrir la app.
REM  NO cierres la ventana negra mientras uses la app.
REM ============================================================
cd /d "%~dp0"
echo.
echo   Iniciando Prometeo - Extractor de candidatos...
echo   La app se abrira sola en tu navegador (http://localhost:8501)
echo   Para CERRAR la app: cierra esta ventana negra.
echo.
python -m streamlit run app.py
pause
