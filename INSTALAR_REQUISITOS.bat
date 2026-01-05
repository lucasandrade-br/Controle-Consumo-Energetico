@echo off
chcp 65001 > nul
title Instalador - Sistema de Monitoramento de Energia
color 0A

echo.
echo ====================================================
echo     INSTALAÇÃO - Sistema de Monitoramento de Energia
echo ====================================================
echo.
echo [INFO] Verificando Python...
python --version
if errorlevel 1 (
    echo.
    echo [ERRO] Python não encontrado!
    echo Por favor, instale o Python 3.8+ em python.org
    echo.
    pause
    exit /b 1
)

echo.
echo [INFO] Instalando dependências do projeto...
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERRO] Falha na instalação dos requisitos!
    echo.
    pause
    exit /b 1
)

echo.
echo ====================================================
echo     INSTALAÇÃO CONCLUÍDA COM SUCESSO!
echo ====================================================
echo.
echo Agora você pode executar o sistema usando:
echo   - INICIAR_SISTEMA.bat
echo.
pause
