@echo off
chcp 65001 >nul
title GR4 HDF 재고 감시 - 설치 및 실행
cd /d "%~dp0"

echo [1/3] Python 확인 중...
where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set PY=python
    ) else (
        echo.
        echo Python이 설치되어 있지 않습니다.
        echo https://www.python.org/downloads/ 에서 Python 3을 설치한 뒤 다시 실행하세요.
        echo 설치 시 "Add python.exe to PATH"를 체크하세요.
        pause
        exit /b 1
    )
)

echo [2/3] 필요한 패키지 설치 중...
%PY% -m pip install --upgrade requests beautifulsoup4 winotify
if errorlevel 1 (
    echo 패키지 설치에 실패했습니다.
    pause
    exit /b 1
)

echo [3/3] 재고 감시를 시작합니다.
echo 창을 닫거나 Ctrl+C를 누르면 종료됩니다.
echo.
%PY% "%~dp0gr4_stock_monitor.py"

echo.
pause
