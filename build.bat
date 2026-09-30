@echo off
REM Gera o RFQ_Control.exe com o PyInstaller (requer Python 3.11 ou superior).
REM Resultado: dist\RFQ_Control\  (RFQ_Control.exe + programa\ + dados\)
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Criando ambiente virtual...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if errorlevel 1 (
        echo Nao foi possivel criar o ambiente virtual. Instale o Python 3.11+ de python.org.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
if errorlevel 1 (
    echo Falha ao instalar as dependencias.
    pause
    exit /b 1
)

python build.py
if errorlevel 1 (
    echo Falha ao gerar o executavel.
    pause
    exit /b 1
)

echo.
echo Executavel gerado em dist\RFQ_Control\RFQ_Control.exe
pause
