"""
Processos judiciais via DJEN — Comunicações Processuais (CNJ/PJe).

Por que NÃO usamos a API pública do DataJud: ela não expõe as partes do
processo (o glossário oficial não tem CPF/CNPJ nem nome — Portaria CNJ
160/2020), então é impossível achar processos por CNPJ. Ver a análise em
docs/DATAJUD-vs-DJEN.md.

A Comunica API do DJEN (Diário de Justiça Eletrônico Nacional), por outro
lado, permite buscar publicações por NOME da parte. Como temos a razão social
de todas as empresas, consultamos por nome, CONFIRMAMOS que a empresa está
entre os `destinatarios` (evita homônimo) e guardamos os processos distintos.

Limites honestos:
  - cobertura ~2022+ (era do DJEN) — pega litígio recente/ativo, não histórico;
  - casamento por NOME, não CNPJ (mitigado pela confirmação nos destinatários);
Fonte: https://comunicaapi.pje.jus.br/api/v1 (CNJ/PJe) — sem chave, gratuita.
"""
import time
import unicodedata

import requests

import config
from src import db_utils, checkpoint

CHECKPOINT_NAME = "djen_processados"
BASE = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
UA = {"User-Agent": "Mozilla/5.0 (compatible; grande-vitoria-dataset/1.0)"}
ITENS_POR_PAGINA = 100
MAX_PAGINAS = 5          # teto por empresa (evita gigantes com 10 mil publicações)
SLEEP_PAGINA = 0.5       # educado com a API pública (ela dá 429 acima de ~2 req/s)
SLEEP_EMPRESA = 0.6      # ~1 req/s no total → evita a maioria dos 429
LOTE = 30                # commit + checkpoint a cada N empresas (durável/retomável)

_POLO = {"A": "Autor", "P": "Réu", "T": "Terceiro"}


def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def _consultar(nome: str, pagina: int, tentativa: int = 0):
    params = {"nomeParte": nome, "itensPorPagina": ITENS_POR_PAGINA, "pagina": pagina}
    try:
        r = requests.get(BASE, params=params, headers=UA, timeout=40)
        if r.status_code == 429:
            if tentativa >= 4:
                return None
            time.sleep(2 ** tentativa)
            return _consultar(nome, pagina, tentativa + 1)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def _processos_da_empresa(razao_social: str) -> dict:
    """Retorna {numero_processo: registro} dos processos onde a razão social
    está confirmada entre os destinatários da publicação."""
    alvo = _norm(razao_social)
    if len(alvo) < 6:
        return {}  # nome curto demais → risco alto de falso positivo
    achados = {}
    for pagina in range(1, MAX_PAGINAS + 1):
        data = _consultar(razao_social, pagina)
        if not data:
            break
        itens = data.get("items") or []
        if not itens:
            break
        for it in itens:
            polo = None
            for d in (it.get("destinatarios") or []):
                if _norm(d.get("nome")) == alvo:
                    polo = _POLO.get((d.get("polo") or "").strip().upper())
                    break
            if polo is None:
                continue  # a empresa não é parte confirmada nesta publicação
            num = it.get("numero_processo")
            if not num:
                continue
            data_pub = it.get("data_disponibilizacao") or ""
            reg = achados.get(num)
            if reg is None or data_pub > (reg["data_ultima_movimentacao"] or ""):
                achados[num] = {
                    "numero_processo": num,
                    "tribunal": it.get("siglaTribunal"),
                    "classe": it.get("nomeClasse"),
                    "assunto": None,
                    "polo": polo,
                    "status": None,
                    "data_ultima_movimentacao": data_pub,
                    "match_confianca": "nome",
                }
        total = data.get("count") or 0
        if pagina * ITENS_POR_PAGINA >= total:
            break
        time.sleep(SLEEP_PAGINA)
    return achados


def executar(limite_cnpjs: int = None, parte: str = None):
    with db_utils.get_conn() as conn:
        empresas = db_utils.listar_cnpjs(conn)

    empresas = sorted(empresas, key=lambda e: e["cnpj"])
    if parte:
        i, n = (int(x) for x in parte.split("/"))
        empresas = [e for idx, e in enumerate(empresas) if idx % n == (i - 1)]
        print(f"[djen_client] Fatia {i}/{n}: {len(empresas)} empresas desta máquina.")

    processados = set(checkpoint.carregar(CHECKPOINT_NAME))
    pendentes = [e for e in empresas if e["cnpj"] not in processados]
    if limite_cnpjs:
        pendentes = pendentes[:limite_cnpjs]

    print(f"[djen_client] {len(pendentes)} empresas pendentes de consulta (de {len(empresas)}).")

    # Buffer + flush em lote: minimiza contenção do lock de escrita com o geo,
    # que segura o lock por lotes longos. busy_timeout alto pra aguardar o geo.
    buffer = []          # (cnpj, [registros])
    total_proc = 0
    processadas_desde_flush = 0

    def _flush():
        nonlocal buffer, processadas_desde_flush
        if buffer:
            with db_utils.get_conn() as conn:
                conn.execute("PRAGMA busy_timeout=300000")  # espera o lote do geo (~100s)
                for cnpj, regs in buffer:
                    # idempotente: remove os do DJEN antes de reinserir esta empresa
                    conn.execute("DELETE FROM processos_judiciais "
                                 "WHERE cnpj_empresa=? AND match_confianca='nome'", (cnpj,))
                    for reg in regs:
                        db_utils.insert_generic(conn, "processos_judiciais", {"cnpj_empresa": cnpj, **reg})
                conn.commit()
            buffer = []
        # checkpoint SEMPRE avança (mesmo sem processos no lote) — durável a quedas
        checkpoint.salvar(CHECKPOINT_NAME, processados)
        processadas_desde_flush = 0

    for e in pendentes:
        cnpj, razao = e["cnpj"], (e["razao_social"] or "")
        try:
            achados = _processos_da_empresa(razao)
        except Exception as exc:
            print(f"[djen_client] erro em {cnpj} ({razao[:30]}): {exc}")
            achados = {}
        if achados:
            buffer.append((cnpj, list(achados.values())))
            total_proc += len(achados)
        processados.add(cnpj)
        processadas_desde_flush += 1
        if processadas_desde_flush >= LOTE:
            _flush()
            print(f"[djen_client] {len(processados)} empresas consultadas · "
                  f"{total_proc} processos vinculados nesta execução.")
        time.sleep(SLEEP_EMPRESA)

    _flush()
    print(f"[djen_client] Concluído: {total_proc} processos vinculados nesta execução.")


if __name__ == "__main__":
    executar()
