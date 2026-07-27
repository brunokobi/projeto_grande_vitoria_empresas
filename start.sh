#!/usr/bin/env bash
# Start do app em produção (Coolify): baixa o dataset se ainda não existir
# (persistido via volume) e sobe a API/dashboard. Usa só a stdlib do Python
# pra baixar/descompactar, sem depender de curl/gunzip estarem na imagem.
set -e
cd "$(dirname "$0")"

RELEASE_URL="https://github.com/brunokobi/projeto_grande_vitoria_empresas/releases/download/dataset-latest/grande_vitoria.db.gz"

mkdir -p data
if [ ! -f data/grande_vitoria.db ]; then
    python -c "import urllib.request; urllib.request.urlretrieve('$RELEASE_URL', 'data/grande_vitoria.db.gz')"
    python -c "import gzip, shutil; shutil.copyfileobj(gzip.open('data/grande_vitoria.db.gz', 'rb'), open('data/grande_vitoria.db', 'wb'))"
    rm -f data/grande_vitoria.db.gz
fi

exec uvicorn api:app --host 0.0.0.0 --port 8000
