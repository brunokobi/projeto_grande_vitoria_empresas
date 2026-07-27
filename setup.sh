#!/usr/bin/env bash
# Setup do repositório de consumo: cria o venv (via uv, com Python 3.12 isolado),
# instala dependências e baixa o dataset (publicado como GitHub Release). Rode
# uma vez após clonar:
#     bash setup.sh
set -e
cd "$(dirname "$0")"

RELEASE_URL="https://github.com/brunokobi/projeto_grande_vitoria_empresas/releases/download/dataset-latest/grande_vitoria.db.gz"

# uv (https://docs.astral.sh/uv/) gerencia o próprio Python (3.12, isolado do
# sistema) — não depende da versão de "python3" já instalada nem de pacotes do
# gerenciador do SO (o pacote "mcp" exige Python 3.10+, e PPAs como a deadsnakes
# já não publicam mais builds novos para distros mais antigas, ex.: Ubuntu 20.04).
UV_BIN="$(command -v uv || true)"
for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    [ -n "$UV_BIN" ] && break
    [ -x "$candidate" ] && UV_BIN="$candidate"
done

if [ -z "$UV_BIN" ]; then
    echo "==> Instalando uv (gerenciador de Python/dependências)"
    if ! command -v curl >/dev/null 2>&1; then
        echo "Erro: curl não encontrado. Instale curl e rode 'bash setup.sh' de novo." >&2
        exit 1
    fi
    curl -LsSf https://astral.sh/uv/install.sh | sh
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        [ -x "$candidate" ] && UV_BIN="$candidate" && break
    done
fi

if [ -z "$UV_BIN" ]; then
    echo "Erro: não foi possível instalar/localizar o uv. Instale manualmente em https://docs.astral.sh/uv/ e rode 'bash setup.sh' de novo." >&2
    exit 1
fi

echo "==> Criando ambiente virtual (.venv, Python 3.12)"
if [ ! -f .venv/bin/activate ]; then
    rm -rf .venv
    "$UV_BIN" venv --python 3.12 .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Instalando dependências"
"$UV_BIN" pip install -q -r requirements.txt

echo "==> Baixando o dataset (GitHub Release)"
mkdir -p data
if [ -f data/grande_vitoria.db ]; then
    echo "    data/grande_vitoria.db já existe, mantido."
else
    if ! command -v curl >/dev/null 2>&1; then
        echo "Erro: curl não encontrado. Instale curl e rode 'bash setup.sh' de novo." >&2
        exit 1
    fi
    curl -L --fail -o data/grande_vitoria.db.gz "$RELEASE_URL"
    gunzip -f data/grande_vitoria.db.gz
    echo "    data/grande_vitoria.db pronto."
fi

echo ""
echo "Pronto! Para abrir o dashboard + API:"
echo "    source .venv/bin/activate && uvicorn api:app"
echo "    -> http://localhost:8000"
echo "O servidor MCP é detectado automaticamente pelo Claude Code (.mcp.json)."
