"""
Atualiza data/grande_vitoria.db com a versão mais recente do Release público,
sem precisar reiniciar o servidor. Baixa pra um arquivo temporário e substitui
via os.replace (atômico), então uma query em andamento nunca vê um arquivo
parcialmente escrito.

Chamado por uma Scheduled Task do Coolify a cada 2h — o pipeline de extração
(repo privado) publica no mesmo Release nessa cadência.
"""
import gzip
import os
import shutil
import urllib.request

RELEASE_URL = "https://github.com/brunokobi/projeto_grande_vitoria_empresas/releases/download/dataset-latest/grande_vitoria.db.gz"

base = os.path.dirname(os.path.abspath(__file__))
gz_tmp = os.path.join(base, "data", "grande_vitoria.db.gz.new")
db_tmp = os.path.join(base, "data", "grande_vitoria.db.new")
db_final = os.path.join(base, "data", "grande_vitoria.db")

urllib.request.urlretrieve(RELEASE_URL, gz_tmp)
with gzip.open(gz_tmp, "rb") as fi, open(db_tmp, "wb") as fo:
    shutil.copyfileobj(fi, fo)
os.replace(db_tmp, db_final)
os.remove(gz_tmp)
print("[refresh_dataset] Atualizado:", db_final)
