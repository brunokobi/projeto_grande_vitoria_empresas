"""
Atualiza data/grande_vitoria.db com a versão mais recente do Release público,
sem precisar reiniciar o servidor. Baixa pra um arquivo temporário e substitui
via os.replace (atômico), então uma query em andamento nunca vê um arquivo
parcialmente escrito.

Chamado pelo cron do usuário ubuntu na vpsrafa a cada 2h (minuto 30, depois
do vps-publicar-2h.sh do pipeline de extração, que publica no minuto 0).
Só baixa quando o asset do Release mudou (data de atualização do asset
guardada em data/.dataset_release); `--force` baixa de qualquer jeito.
"""
import gzip
import json
import os
import shutil
import sys
import urllib.request

RELEASE_URL = "https://github.com/brunokobi/projeto_grande_vitoria_empresas/releases/download/dataset-latest/grande_vitoria.db.gz"
RELEASE_API = "https://api.github.com/repos/brunokobi/projeto_grande_vitoria_empresas/releases/tags/dataset-latest"

base = os.path.dirname(os.path.abspath(__file__))
gz_tmp = os.path.join(base, "data", "grande_vitoria.db.gz.new")
db_tmp = os.path.join(base, "data", "grande_vitoria.db.new")
db_final = os.path.join(base, "data", "grande_vitoria.db")
marcador = os.path.join(base, "data", ".dataset_release")


def _versao_publicada():
    """updated_at + tamanho do asset no Release, ou None se a API falhar
    (aí baixa mesmo assim — melhor gastar banda que ficar desatualizado)."""
    try:
        req = urllib.request.Request(RELEASE_API, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            rel = json.load(r)
        asset = next(a for a in rel["assets"] if a["name"] == "grande_vitoria.db.gz")
        return f'{asset["updated_at"]} {asset["size"]}'
    except Exception as e:
        print("[refresh_dataset] Não consegui consultar a versão do Release:", e)
        return None


versao = _versao_publicada()
if versao and "--force" not in sys.argv and os.path.exists(db_final):
    try:
        with open(marcador) as f:
            if f.read().strip() == versao:
                print("[refresh_dataset] Release sem mudança desde a última atualização — nada a fazer.")
                sys.exit(0)
    except FileNotFoundError:
        pass

urllib.request.urlretrieve(RELEASE_URL, gz_tmp)
with gzip.open(gz_tmp, "rb") as fi, open(db_tmp, "wb") as fo:
    shutil.copyfileobj(fi, fo)
os.replace(db_tmp, db_final)
os.remove(gz_tmp)
if versao:
    with open(marcador, "w") as f:
        f.write(versao)
print("[refresh_dataset] Atualizado:", db_final)
