"""
Pré-cálculo da nota de integridade de TODAS as empresas, pra filtrar/contar
por nível no dashboard (o modal continua calculando na hora).

Integridade dos dados:
  - A nota de cada empresa vem de `dataset_queries.obter_empresa(cnpj)`, que já
    chama `avaliacao_integridade.avaliar` — exatamente o mesmo caminho do modal,
    sobre o MESMO arquivo de banco. Nada é estimado ou aproximado.
  - Só empresas com algum registro nas tabelas que a nota usa podem pontuar
    (`_TABELAS_QUE_PONTUAM`). As demais recebem nota 0 / nível mais baixo — e
    isso é CONFERIDO numa amostra aleatória rodando a função de verdade; se
    alguma der diferente, a tabela não é gravada (o filtro fica desligado).
  - A tabela `integridade_meta` guarda a versão da metodologia. O dashboard só
    usa o pré-cálculo se a versão bater com a do código em execução
    (`dataset_queries._integridade_ok`), senão o filtro some em vez de mostrar
    nota de outra metodologia.

Rodado pelo refresh_dataset.py no arquivo novo ANTES da troca atômica, então
banco e notas são sempre da mesma versão do dataset.

Uso manual:  python -m src.integridade_lote caminho/do/banco.db
"""
from __future__ import annotations

import contextlib
import random
import sqlite3
import sys
import time
from pathlib import Path

import config

_TABELAS_QUE_PONTUAM = (
    "sancoes_administrativas", "ocorrencias_socios", "dividas_ativas",
    "processos_judiciais", "infracoes_ambientais", "vinculos_politicos",
    "contratos_pncp", "contratos_governamentais",
)
_AMOSTRA_CONFERENCIA = 500


class IntegridadeInconsistente(RuntimeError):
    pass


def gerar(db_path: str | Path, log=print) -> dict:
    db_path = Path(db_path)
    config.DB_PATH = db_path  # dataset_queries lê config.DB_PATH a cada conexão
    from src import avaliacao_integridade, dataset_queries as dq

    nivel_zero = avaliacao_integridade.NIVEIS[-1][1]
    t0 = time.time()
    # contextlib.closing: o `with sqlite3.connect()` sozinho NÃO fecha a conexão,
    # e uma conexão de leitura aberta impede o checkpoint do WAL no fim.
    with contextlib.closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as c:
        existentes = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        tabelas = [t for t in _TABELAS_QUE_PONTUAM if t in existentes]
        uniao = " UNION ".join(f"SELECT cnpj_empresa FROM {t}" for t in tabelas)
        candidatos = [r[0] for r in c.execute(
            f"SELECT e.cnpj FROM empresas e JOIN ({uniao}) x ON x.cnpj_empresa = e.cnpj "
            "GROUP BY e.cnpj")]
        total_empresas = c.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
        set_cand = set(candidatos)
        sem_registro = [r[0] for r in c.execute("SELECT cnpj FROM empresas")
                        if r[0] not in set_cand]
    log(f"[integridade] {len(candidatos)} empresas com algum registro a avaliar "
        f"(de {total_empresas}).")

    # Conferência: empresa sem registro nenhum TEM que dar nota 0 pela função real.
    amostra = random.sample(sem_registro, min(_AMOSTRA_CONFERENCIA, len(sem_registro)))
    for cnpj in amostra:
        av = dq.obter_empresa(cnpj)["avaliacao_integridade"]
        if av["nota"] != 0:
            raise IntegridadeInconsistente(
                f"{cnpj} não tem registro nas tabelas de risco mas a nota deu {av['nota']} — "
                "alguma regra nova usa outra tabela; atualize _TABELAS_QUE_PONTUAM.")

    linhas = []
    for i, cnpj in enumerate(candidatos, 1):
        d = dq.obter_empresa(cnpj)
        if d is None:
            continue
        av = d["avaliacao_integridade"]
        linhas.append((cnpj, int(av["nota"]), av["nivel"], len(av["impeditivos"])))
        if i % 20000 == 0:
            log(f"[integridade] {i}/{len(candidatos)} ({time.time() - t0:.0f}s)")

    # Tudo numa transação explícita: ou grava as duas tabelas completas, ou nada.
    c = sqlite3.connect(db_path, isolation_level=None)
    try:
        c.execute("BEGIN")
        c.execute("DROP TABLE IF EXISTS integridade_empresas")
        c.execute("DROP TABLE IF EXISTS integridade_meta")
        c.execute("CREATE TABLE integridade_empresas (cnpj TEXT PRIMARY KEY, nota INTEGER NOT NULL, "
                  "nivel TEXT NOT NULL, qtd_impeditivos INTEGER NOT NULL) WITHOUT ROWID")
        c.executemany("INSERT INTO integridade_empresas VALUES (?,?,?,?)", linhas)
        c.executemany("INSERT INTO integridade_empresas VALUES (?,0,?,0)",
                      ((cnpj, nivel_zero) for cnpj in sem_registro))
        n = c.execute("SELECT COUNT(*) FROM integridade_empresas").fetchone()[0]
        if n != total_empresas:
            raise IntegridadeInconsistente(f"{n} notas gravadas para {total_empresas} empresas.")
        c.execute("CREATE INDEX idx_integridade_nivel ON integridade_empresas(nivel)")
        c.execute("CREATE TABLE integridade_meta (versao TEXT, gerado_em TEXT, "
                  "qtd_empresas INTEGER, qtd_avaliadas INTEGER, amostra_conferida INTEGER)")
        c.execute("INSERT INTO integridade_meta VALUES (?,?,?,?,?)",
                  (avaliacao_integridade.VERSAO, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   total_empresas, len(linhas), len(amostra)))
        por_nivel = dict(c.execute("SELECT nivel, COUNT(*) FROM integridade_empresas GROUP BY nivel"))
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        c.close()
        raise
    # O banco publicado vem em modo WAL: sem isto as tabelas novas podem ficar só
    # no arquivo -wal (que não acompanha o os.replace do refresh). DELETE força o
    # checkpoint e grava tudo no arquivo principal.
    modo = c.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
    c.close()
    if modo.lower() != "delete":
        raise IntegridadeInconsistente(f"não consegui tirar o banco do modo WAL (ficou {modo}).")
    log(f"[integridade] OK em {time.time() - t0:.0f}s — {por_nivel}")
    return por_nivel


if __name__ == "__main__":
    gerar(sys.argv[1] if len(sys.argv) > 1 else config.DB_PATH)
