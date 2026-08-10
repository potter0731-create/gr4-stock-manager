@echo off
chcp 65001 >nul
title GR4 HDF 재고 감시
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0gr4_stock_monitor.py"
) else (
    python "%~dp0gr4_stock_monitor.py"
)
pause
