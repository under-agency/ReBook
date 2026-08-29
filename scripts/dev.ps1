# Поднимает dev-окружение ReBook: Postgres (WSL), бэкенд, фронт, бот+воркер.
# Запуск:  powershell -File scripts\dev.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root "apps\backend\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Не найдено venv бэкенда. Сначала:" -ForegroundColor Yellow
    Write-Host "  py -3.13 -m venv apps\backend\.venv"
    Write-Host "  apps\backend\.venv\Scripts\python.exe -m pip install -r apps\backend\requirements.txt"
    exit 1
}

Write-Host "→ Postgres в WSL…" -ForegroundColor Cyan
wsl.exe -d Ubuntu -u root service postgresql start | Out-Null

Write-Host "→ Бэкенд на :8000" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "`$env:PYTHONUTF8=1; Set-Location '$root\apps\backend'; & '$py' -m uvicorn app.main:app --reload --port 8000"

Write-Host "→ Фронт на :5173" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root\apps\web'; npm run dev"

Write-Host "→ Бот и воркер" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "`$env:PYTHONUTF8=1; Set-Location '$root\apps\backend'; & '$py' -m app.run_bot"

Write-Host ""
Write-Host "Кабинет: http://localhost:5173" -ForegroundColor Green
Write-Host "  владелец   owner@demo.ru / owner12345"
Write-Host "  админ      staff@demo.ru / staff12345"
Write-Host "  superadmin admin@rebook.ru / admin12345"
