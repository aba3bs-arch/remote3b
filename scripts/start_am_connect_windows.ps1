$ErrorActionPreference = "Stop"

Write-Host "== AM-Connect Windows setup ==" -ForegroundColor Cyan

function Resolve-Python {
    $python = Get-Command py -ErrorAction SilentlyContinue
    if ($python) {
        return "py"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return "python"
    }

    throw "Python no esta instalado o no esta en PATH. Instala Python desde https://www.python.org/downloads/ y marca 'Add python.exe to PATH'."
}

$PythonCmd = Resolve-Python

if (!(Test-Path "venv")) {
    Write-Host "Creando entorno virtual..." -ForegroundColor Yellow
    & $PythonCmd -m venv venv
}

$VenvPython = Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"
if (!(Test-Path $VenvPython)) {
    throw "No se encontro $VenvPython. Borra la carpeta venv y vuelve a ejecutar este script."
}

Write-Host "Instalando dependencias..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Se creo .env desde .env.example" -ForegroundColor Green
}

$env:HOST = "0.0.0.0"
$env:PORT = "8000"

Write-Host ""
Write-Host "AM-Connect esta iniciando..." -ForegroundColor Green
Write-Host "Abre en tu navegador: http://localhost:8000" -ForegroundColor Green
Write-Host "Deja esta ventana abierta. Para apagar, presiona Ctrl+C." -ForegroundColor Yellow
Write-Host ""

& $VenvPython server/main.py
