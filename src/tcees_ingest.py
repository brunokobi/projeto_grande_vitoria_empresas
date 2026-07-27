"""
Ingestão das listas de responsáveis/sanções estaduais do TCEES (Tribunal
de Contas do Estado do Espírito Santo), via portal de dados abertos do ES.

São quatro listas, todas gravadas na tabela `sancoes_administrativas` já
existente, distinguidas pelo campo `tipo`:
  - TCEES - Empresa Inidônea
  - TCEES - Proibido de Contratar
  - TCEES - Inabilitado
  - TCEES - Contas Irregulares

Diferença em relação ao CEIS/CNEP (sanctions_ingest.py): aquelas são
sanções FEDERAIS (Portal da Transparência/CGU); estas são ESTADUAIS
(Tribunal de Contas do ES) e não aparecem na base federal.

As listas contêm tanto pessoas físicas (CPF) quanto jurídicas (CNPJ) como
responsáveis — só vinculamos quando o documento bate com um CNPJ já
carregado da base da Receita Federal. Documentos que são CPF de pessoa
física responsável simplesmente não encontram par e são ignorados (correto:
o dataset é de empresas).
"""
from pathlib import Path

import requests
import pandas as pd

import config
from src import db_utils, matching


def _baixar_csv(url: str, destino: Path) -> Path:
    if destino.exists():
        print(f"[tcees_ingest] {destino.name} já baixado, pulando.")
        return destino
    print(f"[tcees_ingest] Baixando {url} ...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    destino.write_bytes(resp.content)
    return destino


def _processar_lista(caminho_csv: Path, tipo: str, cnpjs_validos: set) -> int:
    # dump do CKAN vem separado por vírgula, encoding utf-8 com BOM
    df = pd.read_csv(caminho_csv, encoding="utf-8-sig", dtype=str, sep=",")
    df.columns = [c.strip() for c in df.columns]

    # Prioriza a coluna que contém o NÚMERO do documento (não a que diz o
    # TIPO). "NumeroDocumento..." tem que vir antes de qualquer match com
    # "...Documento..." para não pegar 'TipoDocumentoResponsavel' por engano.
    col_doc = next((c for c in df.columns if "NumeroDocumento" in c), None)
    if col_doc is None:
        col_doc = next(
            (c for c in df.columns if "Documento" in c and "Tipo" not in c),
            None,
        )
    if col_doc is None:
        raise RuntimeError(
            f"Coluna de documento não encontrada em {tipo}. "
            f"Colunas: {list(df.columns)}"
        )

    total = 0
    with db_utils.get_conn() as conn:
        for _, row in df.iterrows():
            cnpj = matching.normalizar_cnpj(row.get(col_doc, ""))
            # CNPJ tem 14 dígitos; documentos de 11 são CPF de pessoa física
            # responsável — ignoramos, pois o dataset é de empresas.
            if len(cnpj) != 14 or cnpj not in cnpjs_validos:
                continue
            processo = row.get("NumeroProcesso", "")
            ano = row.get("AnoProcesso", "")
            registro = {
                "cnpj_empresa": cnpj,
                "tipo": tipo,
                "motivo": row.get("TipoDeliberacao", ""),
                "orgao_sancionador": f"TCEES ({row.get('Jurisdicionado', '')})".strip(),
                "data_inicio": row.get("DataTransito", ""),
                "data_fim": row.get("DataTermino", ""),
                "valor_multa": None,
                "numero_processo": processo,
                "ano_processo": ano,
                "numero_deliberacao": row.get("NumeroDeliberacao", ""),
                "ano_deliberacao": row.get("AnoDeliberacao", ""),
                "match_confianca": "direto",
            }
            db_utils.insert_generic(conn, "sancoes_administrativas", registro)
            total += 1
    print(f"[tcees_ingest] {tipo}: {total} registros vinculados a empresas da base.")
    return total


def executar():
    with db_utils.get_conn() as conn:
        cnpjs_validos = {r["cnpj"] for r in db_utils.listar_cnpjs(conn)}

    if not cnpjs_validos:
        print("[tcees_ingest] Nenhum CNPJ carregado ainda — rode cnpj_ingest primeiro.")
        return

    raw_dir = config.DATA_RAW_DIR / "tcees"
    raw_dir.mkdir(exist_ok=True)

    total_geral = 0
    for tipo, resource_id in config.TCEES_LISTAS.items():
        url = config.TCEES_DUMP_URL_TEMPLATE.format(resource_id=resource_id)
        nome_arquivo = f"{resource_id}.csv"
        try:
            caminho = _baixar_csv(url, raw_dir / nome_arquivo)
            total_geral += _processar_lista(caminho, tipo, cnpjs_validos)
        except (requests.RequestException, RuntimeError) as e:
            print(f"[tcees_ingest] Falha em '{tipo}': {e}")

    print(f"[tcees_ingest] Total: {total_geral} sanções estaduais do TCEES vinculadas.")


if __name__ == "__main__":
    executar()
