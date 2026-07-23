"""
Consulta de processos judiciais via API pública do DataJud (CNJ).

Diferente das fontes anteriores, o DataJud NÃO tem "baixe tudo" — é uma
API de busca (Elasticsearch por trás) que precisa ser consultada
CNPJ por CNPJ, por tribunal. Isso implica:
  - rate limit (respeitado via sleep + backoff exponencial em erro 429)
  - checkpoint por CNPJ+tribunal já consultado (retomável)
  - iterar sobre múltiplos tribunais relevantes (TJES, TRT17, TRF2, etc.)

Documentação oficial: https://datajud-wiki.cnj.jus.br/api-publica/
"""
import time

import requests

import config
from src import db_utils, checkpoint

CHECKPOINT_NAME = "datajud_processados"


class DataJudAuthError(Exception):
    pass


def _query_body(cnpj: str) -> dict:
    """
    Monta a query Elasticsearch para buscar processos onde o CNPJ aparece
    como parte. O campo exato depende do tribunal (nem todos indexam
    'partes.documento' da mesma forma) — ajustar conforme resposta real
    de cada api_publica_<tribunal>.
    """
    return {
        "query": {
            "match": {
                "partes.documento": cnpj
            }
        },
        "size": 50,
    }


def _consultar_tribunal(tribunal_key: str, alias: str, cnpj: str, tentativa: int = 0) -> list:
    url = f"{config.DATAJUD_BASE_URL}/{alias}/_search"
    headers = {
        "Authorization": f"APIKey {config.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, json=_query_body(cnpj), headers=headers, timeout=30)

        if resp.status_code in (401, 403):
            raise DataJudAuthError(
                f"Erro {resp.status_code} de autenticação — a chave pública do DataJud "
                f"provavelmente mudou. Pegue a atualizada em {config.DATAJUD_WIKI_URL} e "
                f"defina a variável de ambiente DATAJUD_API_KEY com o novo valor."
            )

        if resp.status_code == 429:
            if tentativa >= 5:
                print(f"[datajud_client] Rate limit persistente para {cnpj}/{tribunal_key}, desistindo.")
                return []
            espera = config.DATAJUD_RATE_LIMIT_SLEEP_SECONDS * (2 ** tentativa)
            print(f"[datajud_client] 429 recebido, aguardando {espera:.1f}s (tentativa {tentativa+1})")
            time.sleep(espera)
            return _consultar_tribunal(tribunal_key, alias, cnpj, tentativa + 1)

        resp.raise_for_status()
        data = resp.json()
        return data.get("hits", {}).get("hits", [])
    except requests.RequestException as e:
        print(f"[datajud_client] Erro consultando {tribunal_key} para {cnpj}: {e}")
        return []


def _hit_para_registro(cnpj: str, tribunal_key: str, hit: dict) -> dict:
    fonte = hit.get("_source", {})
    return {
        "cnpj_empresa": cnpj,
        "numero_processo": fonte.get("numeroProcesso"),
        "tribunal": tribunal_key,
        "classe": (fonte.get("classe") or {}).get("nome"),
        "assunto": ", ".join(a.get("nome", "") for a in fonte.get("assuntos", [])),
        "polo": None,  # requer inspecionar 'partes' e comparar documento com cnpj
        "status": None,
        "data_ultima_movimentacao": fonte.get("dataHoraUltimaAtualizacao"),
        "match_confianca": "direto",
    }


def executar(limite_cnpjs: int = None):
    """
    limite_cnpjs: útil para rodar em lotes menores durante testes, dado
    o rate limit — None processa todos os CNPJs pendentes.
    """
    if not config.DATAJUD_API_KEY:
        print("[datajud_client] DATAJUD_API_KEY não configurada — defina a variável de ambiente.")
        return

    with db_utils.get_conn() as conn:
        empresas = db_utils.listar_cnpjs(conn)

    processados = set(checkpoint.carregar(CHECKPOINT_NAME))
    pendentes = [e for e in empresas if e["cnpj"] not in processados]
    if limite_cnpjs:
        pendentes = pendentes[:limite_cnpjs]

    print(f"[datajud_client] {len(pendentes)} CNPJs pendentes de consulta (de {len(empresas)} totais).")

    # Commit + checkpoint em lote a cada N — durável a quedas (não usa uma
    # transação única pro loop inteiro, que perderia tudo num crash). Lote
    # pequeno porque o datajud é lento (rate limit do CNJ).
    LOTE = 25

    def _persistir(conn):
        conn.commit()
        checkpoint.salvar(CHECKPOINT_NAME, processados)

    with db_utils.get_conn() as conn:
        for i, empresa in enumerate(pendentes):
            cnpj = empresa["cnpj"]
            for tribunal_key, alias in config.DATAJUD_TRIBUNAIS.items():
                try:
                    hits = _consultar_tribunal(tribunal_key, alias, cnpj)
                except DataJudAuthError as e:
                    _persistir(conn)  # salva o que já foi feito antes de parar
                    print(f"[datajud_client] {e}")
                    print(
                        f"[datajud_client] Interrompendo a etapa — {i} de "
                        f"{len(pendentes)} CNPJs já processados e salvos no "
                        f"checkpoint. Ajuste DATAJUD_API_KEY e rode de novo "
                        f"para retomar de onde parou."
                    )
                    return
                for hit in hits:
                    registro = _hit_para_registro(cnpj, tribunal_key, hit)
                    db_utils.insert_generic(conn, "processos_judiciais", registro)
                time.sleep(config.DATAJUD_RATE_LIMIT_SLEEP_SECONDS)

            processados.add(cnpj)
            if (i + 1) % LOTE == 0:
                _persistir(conn)
                print(f"[datajud_client] {i+1}/{len(pendentes)} CNPJs consultados (salvo).")
        _persistir(conn)

    print("[datajud_client] Consulta concluída.")


if __name__ == "__main__":
    executar()
