"""
Atualiza data/grande_vitoria.db com a versão mais recente do Release público,
sem precisar reiniciar o servidor. Baixa pra um arquivo temporário e substitui
via os.replace (atômico), então uma query em andamento nunca vê um arquivo
parcialmente escrito.

Chamado pelo cron do usuário ubuntu na vpsrafa a cada 2h (minuto 30, depois
do vps-publicar-2h.sh do pipeline de extração, que publica no minuto 0).
Antes da troca, grava no arquivo novo a nota de integridade de todas as
empresas (src/integridade_lote.py), pro filtro por nível do dashboard.
Só baixa quando o asset do Release mudou (data de atualização do asset
guardada em data/.dataset_release); `--force` baixa de qualquer jeito.
"""
import contextlib
import gzip
import json
import os
import shutil
import sqlite3
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


# Duas execuções ao mesmo tempo (cron + --force manual) escreveriam no mesmo
# .new — a segunda sai sem fazer nada.
import fcntl
_trava = open(os.path.join(base, "data", ".refresh_dataset.lock"), "w")
try:
    fcntl.flock(_trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("[refresh_dataset] Outra atualização já está rodando — saindo.")
    sys.exit(0)

versao = _versao_publicada()
if versao and "--force" not in sys.argv and os.path.exists(db_final):
    try:
        with open(marcador) as f:
            if f.read().strip() == versao:
                print("[refresh_dataset] Release sem mudança desde a última atualização — nada a fazer.")
                sys.exit(0)
    except FileNotFoundError:
        pass

def _remover_auxiliares(caminho):
    """-wal/-shm/-journal de uma execução anterior seriam aplicados pelo SQLite
    ao arquivo NOVO com o mesmo nome — e corrompem a leitura dele."""
    for suf in ("-wal", "-shm", "-journal"):
        try:
            os.remove(caminho + suf)
        except FileNotFoundError:
            pass


def _banco_integro(caminho) -> bool:
    import sqlite3
    try:
        c = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        try:
            ok = c.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            ok = ok and c.execute("SELECT COUNT(*) FROM empresas").fetchone()[0] > 0
        finally:
            c.close()
        return ok
    except sqlite3.Error as e:
        print("[refresh_dataset] Erro ao conferir o banco novo:", repr(e))
        return False


_remover_auxiliares(db_tmp)
urllib.request.urlretrieve(RELEASE_URL, gz_tmp)
with gzip.open(gz_tmp, "rb") as fi, open(db_tmp, "wb") as fo:
    shutil.copyfileobj(fi, fo)

# Índices das consultas por empresa nas tabelas geradas no ETL local. A
# mesclagem já copia os índices do Release, mas um banco publicado antes disso
# chegou sem eles (grupo_economico: 642 mil linhas varridas por empresa — o
# pré-cálculo e o modal ficaram ~37x mais lentos). Idempotente.
_INDICES = (
    ("grupo_economico", "CREATE INDEX IF NOT EXISTS idx_grupo_raiz ON grupo_economico(cnpj_basico)"),
    ("risco_pais_socios", "CREATE INDEX IF NOT EXISTS idx_risco_pais_raiz ON risco_pais_socios(cnpj_basico)"),
)
try:
    with contextlib.closing(sqlite3.connect(db_tmp)) as c:
        tabelas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for tabela, sql in _INDICES:
            if tabela in tabelas:
                c.execute(sql)
        c.commit()
        c.execute("PRAGMA journal_mode=DELETE")
except sqlite3.Error as e:
    print("[refresh_dataset] Não consegui criar os índices:", repr(e))

# Nota de integridade pré-calculada (filtro por nível no dashboard), gravada no
# arquivo NOVO antes da troca — banco e notas sempre da mesma versão. Se falhar
# ou a conferência não bater, publica o banco sem a tabela: o filtro some, mas
# nenhuma nota inconsistente aparece.
sys.path.insert(0, base)
try:
    from src import integridade_lote
    integridade_lote.gerar(db_tmp, log=lambda m: print(m, flush=True))
except Exception as e:
    print("[refresh_dataset] Pré-cálculo da nota de integridade NÃO gravado:", repr(e))

# Nunca troca o banco do site por um arquivo que não passe na conferência do
# SQLite: mantém o atual e sai com erro (o cron tenta de novo na próxima rodada).
if not _banco_integro(db_tmp):
    print("[refresh_dataset] Banco novo REPROVADO no quick_check — mantido o banco atual.")
    os.remove(db_tmp)
    _remover_auxiliares(db_tmp)
    sys.exit(1)
_remover_auxiliares(db_tmp)
os.replace(db_tmp, db_final)
os.remove(gz_tmp)
if versao:
    with open(marcador, "w") as f:
        f.write(versao)
print("[refresh_dataset] Atualizado:", db_final)
