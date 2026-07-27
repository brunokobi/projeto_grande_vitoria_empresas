# Setup do repositório de consumo: cria o venv (via uv, com Python 3.12 isolado),
# instala dependências e baixa o dataset (publicado como GitHub Release). Rode
# uma vez após clonar:
#     powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ReleaseUrl = "https://github.com/brunokobi/projeto_grande_vitoria_empresas/releases/download/dataset-latest/grande_vitoria.db.gz"

# uv (https://docs.astral.sh/uv/) gerencia o próprio Python (3.12, isolado) —
# não precisa de Python pré-instalado no Windows nem de qual versão já existe.
$uvCandidates = @("$env:USERPROFILE\.local\bin\uv.exe", "$env:USERPROFILE\.cargo\bin\uv.exe")

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    foreach ($c in $uvCandidates) {
        if (Test-Path $c) { $uv = Get-Item $c; break }
    }
}

if (-not $uv) {
    Write-Host "==> Instalando uv (gerenciador de Python/dependências)"
    Invoke-Expression (Invoke-RestMethod https://astral.sh/uv/install.ps1)
    foreach ($c in $uvCandidates) {
        if (Test-Path $c) { $uv = Get-Item $c; break }
    }
}

if (-not $uv) {
    Write-Error "Não foi possível instalar/localizar o uv. Instale manualmente em https://docs.astral.sh/uv/ e rode 'setup.ps1' de novo."
    exit 1
}

$uvPath = $uv.Source

Write-Host "==> Criando ambiente virtual (.venv, Python 3.12)"
if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
    if (Test-Path ".venv") { Remove-Item -Recurse -Force ".venv" }
    & $uvPath venv --python 3.12 .venv
}

. ".venv\Scripts\Activate.ps1"

Write-Host "==> Instalando dependências"
& $uvPath pip install -q -r requirements.txt

Write-Host "==> Baixando o dataset (GitHub Release)"
New-Item -ItemType Directory -Force -Path "data" | Out-Null
if (Test-Path "data\grande_vitoria.db") {
    Write-Host "    data\grande_vitoria.db já existe, mantido."
} else {
    Invoke-WebRequest -Uri $ReleaseUrl -OutFile "data\grande_vitoria.db.gz"
    & ".venv\Scripts\python.exe" -c "import gzip, shutil; shutil.copyfileobj(gzip.open('data/grande_vitoria.db.gz', 'rb'), open('data/grande_vitoria.db', 'wb'))"
    Remove-Item "data\grande_vitoria.db.gz"
    Write-Host "    data\grande_vitoria.db pronto."
}

Write-Host ""
Write-Host "Pronto! Para abrir o dashboard + API:"
Write-Host "    .venv\Scripts\Activate.ps1; uvicorn api:app"
Write-Host "    -> http://localhost:8000"
Write-Host "O servidor MCP é detectado automaticamente pelo Claude Code (.mcp.json)."
