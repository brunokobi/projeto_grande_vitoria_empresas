#!/usr/bin/env bash
# Setup plug-and-play: cria o venv, instala dependências, prepara o .env e
# descomprime o banco versionado. Rode uma vez após clonar o repositório:
#     bash setup.sh
set -e
cd "$(dirname "$0")"

echo "==> Criando ambiente virtual (.venv)"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Instalando dependências"
pip install --upgrade pip -q
pip install -q -r requirements.txt

echo "==> Preparando .env"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "    .env criado a partir do modelo — ajuste o NOMINATIM_USER_AGENT."
else
    echo "    .env já existe, mantido."
fi

echo "==> Descomprimindo o banco consolidado"
if [ -f data/grande_vitoria.db ]; then
    echo "    data/grande_vitoria.db já existe, mantido."
elif [ -f data/grande_vitoria.db.gz ]; then
    gunzip -k data/grande_vitoria.db.gz
    echo "    data/grande_vitoria.db restaurado (~139MB)."
else
    echo "    Nenhum banco encontrado — rode 'python main.py --etapa cnpj' para gerar."
fi

echo ""
echo "Pronto. Para usar:"
echo "    source .venv/bin/activate && set -a && source .env && set +a"
echo "    python main.py --etapa datajud   # retoma de onde parou"
echo "    python main.py --etapa geo        # retoma de onde parou"
echo "    python main.py --etapa exportar   # gera output/ quando quiser"
