@echo off
chcp 65001 > nul
title Sistema de Monitoramento de Energia - Servidor
color 0B

echo.
echo ====================================================
echo     SISTEMA DE MONITORAMENTO DE ENERGIA
echo ====================================================
echo.
echo [INFO] Iniciando servidor Flask...
echo.
echo Aguarde alguns segundos...
echo.

python app.py

if errorlevel 1 (
    echo.
    echo ====================================================
    echo [ERRO] Falha ao iniciar o sistema!
    echo ====================================================
    echo.
    echo Possíveis causas:
    echo  1. Python não instalado
    echo  2. Dependências não instaladas
    echo.
    echo Solução:
    echo  - Execute: INSTALAR_REQUISITOS.bat
    echo.
    pause
    exit /b 1
)

pause
