#!/usr/bin/env bash
# Setup do repositório de consumo: cria o venv, instala dependências e baixa
# o dataset (publicado como GitHub Release). Rode uma vez após clonar:
#     bash setup.sh
set -e
cd "$(dirname "$0")"

RELEASE_URL="https://github.com/brunokobi/projeto_grande_vitoria_empresas/releases/download/dataset-latest/grande_vitoria.db.gz"

echo "==> Criando ambiente virtual (.venv)"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Instalando dependências"
pip install --upgrade pip -q
pip install -q -r requirements.txt

echo "==> Baixando o dataset (GitHub Release)"
mkdir -p data
if [ -f data/grande_vitoria.db ]; then
    echo "    data/grande_vitoria.db já existe, mantido."
else
    curl -L --fail -o data/grande_vitoria.db.gz "$RELEASE_URL"
    gunzip -f data/grande_vitoria.db.gz
    echo "    data/grande_vitoria.db pronto."
fi

echo ""
echo "Pronto! Para abrir o dashboard + API:"
echo "    source .venv/bin/activate && uvicorn api:app"
echo "    -> http://localhost:8000"
echo "O servidor MCP é detectado automaticamente pelo Claude Code (.mcp.json)."
