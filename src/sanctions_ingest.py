"""
Ingestão de sanções administrativas (CEIS, CNEP, CEPIM — Portal da
Transparência) e Dívida Ativa da União (PGFN).

Todas essas fontes são CSV de download direto (dados abertos reais),
então o fluxo é: baixar -> ler -> filtrar pelos CNPJs já carregados no
banco (recorte Grande Vitória) -> gravar na tabela satélite correspondente.
"""
import zipfile
from pathlib import Path

import requests
import pandas as pd

import config
from src import checkpoint, db_utils, matching, url_validation

CHECKPOINT_DIVIDA_ATIVA = "pgfn_divida_ativa_arquivos_processados"


def _baixar_csv(url: str, destino: Path) -> Path:
    if destino.exists():
        print(f"[sanctions_ingest] {destino.name} já baixado, pulando.")
        return destino
    print(f"[sanctions_ingest] Baixando {url} ...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    destino.write_bytes(resp.content)
    return destino


def _to_float(valor):
    """Converte valor monetário do CSV (formato BR, ex.: '12.345,67') para float."""
    if valor is None:
        return None
    try:
        return float(str(valor).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _obter_csv(origem: str, destino: Path) -> Path:
    """
    Aceita tanto uma URL http(s) quanto um caminho de arquivo local já
    baixado manualmente (ex.: você clicou 'exportar' no navegador e salvou
    em ~/Downloads/ceis_202606.csv — só apontar esse caminho no .env em
    vez de brigar com a URL dinâmica da página).
    """
    if origem.lower().startswith("http"):
        return _baixar_csv(origem, destino)
    caminho_local = Path(origem).expanduser()
    if not caminho_local.exists():
        raise FileNotFoundError(
            f"Arquivo local não encontrado: {caminho_local}. "
            f"Confira o caminho no .env."
        )
    print(f"[sanctions_ingest] Usando arquivo local {caminho_local}")
    return caminho_local


def processar_ceis_cnep(caminho_csv: Path, tipo: str, cnpjs_validos: set):
    """
    tipo: 'CEIS' ou 'CNEP'.
    Colunas variam por ano/layout do Portal da Transparência — ajustar os
    nomes abaixo conforme o cabeçalho real do arquivo baixado (ele muda
    ocasionalmente; sempre inspecionar o CSV antes de rodar em produção).
    """
    df = pd.read_csv(caminho_csv, sep=";", encoding="latin-1", dtype=str)

    with db_utils.get_conn() as conn:
        for _, row in df.iterrows():
            cnpj_raw = row.get("CPF OU CNPJ DO SANCIONADO", "")
            cnpj = matching.normalizar_cnpj(cnpj_raw)
            if cnpj not in cnpjs_validos:
                continue
            registro = {
                "cnpj_empresa": cnpj,
                "tipo": tipo,
                "motivo": row.get("FUNDAMENTAÇÃO LEGAL") or row.get("TIPO DE SANÇÃO"),
                "orgao_sancionador": row.get("ÓRGÃO SANCIONADOR"),
                "data_inicio": row.get("DATA INÍCIO SANÇÃO"),
                "data_fim": row.get("DATA FINAL SANÇÃO"),
                "valor_multa": None,  # nem sempre presente no CEIS/CNEP
                "match_confianca": "direto",
            }
            db_utils.insert_generic(conn, "sancoes_administrativas", registro)
    print(f"[sanctions_ingest] {tipo} processado.")


def _extrair_csvs_do_zip(zip_path: Path) -> list:
    """Extrai todos os CSVs de dentro do zip (datasets .gov.br costumam vir
    como zip com um ou mais CSVs dentro, não um CSV único)."""
    extract_dir = zip_path.parent / f"{zip_path.stem}_extraido"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        nomes_csv = [n for n in z.namelist() if n.lower().endswith(".csv")]
        z.extractall(extract_dir, members=nomes_csv)
    return [extract_dir / n for n in nomes_csv]


def processar_divida_ativa(caminhos_csv: list, cnpjs_validos: set):
    """
    Dívida Ativa da União (PGFN) — arquivo(s) grande(s) (GBs cada), ler em
    chunks. Faz commit e marca checkpoint por arquivo (não uma única
    transação pra tudo) — cada CSV pode levar minutos pra processar, e se o
    processo cair no meio (queda de sessão, etc.), os arquivos já
    concluídos não precisam ser reprocessados nem duplicam registros.
    """
    processados = checkpoint.carregar(CHECKPOINT_DIVIDA_ATIVA)
    total = 0
    for caminho_csv in caminhos_csv:
        if caminho_csv.name in processados:
            print(f"[sanctions_ingest] {caminho_csv.name} já processado, pulando.")
            continue

        total_arquivo = 0
        with db_utils.get_conn() as conn:
            reader = pd.read_csv(
                caminho_csv, sep=";", encoding="latin-1", dtype=str, chunksize=100_000
            )
            for chunk in reader:
                col_cnpj = "CPF_CNPJ" if "CPF_CNPJ" in chunk.columns else chunk.columns[0]
                chunk["cnpj_norm"] = chunk[col_cnpj].fillna("").apply(matching.normalizar_cnpj)
                filtrado = chunk[chunk["cnpj_norm"].isin(cnpjs_validos)]
                for _, row in filtrado.iterrows():
                    registro = {
                        "cnpj_empresa": row["cnpj_norm"],
                        "orgao": "PGFN",
                        "valor": _to_float(row.get("VALOR_CONSOLIDADO")),
                        "situacao": row.get("SITUACAO_INSCRICAO", ""),
                        "data_inscricao": row.get("DATA_INSCRICAO", ""),
                    }
                    db_utils.insert_generic(conn, "dividas_ativas", registro)
                    total_arquivo += 1

        checkpoint.marcar_processado(CHECKPOINT_DIVIDA_ATIVA, caminho_csv.name)
        total += total_arquivo
        print(f"[sanctions_ingest] {caminho_csv.name}: {total_arquivo} registros vinculados "
              f"(total acumulado: {total}).")

    print(f"[sanctions_ingest] {total} registros de dívida ativa vinculados nesta execução.")


def executar():
    with db_utils.get_conn() as conn:
        cnpjs_validos = {r["cnpj"] for r in db_utils.listar_cnpjs(conn)}

    if not cnpjs_validos:
        print("[sanctions_ingest] Nenhum CNPJ carregado ainda — rode cnpj_ingest primeiro.")
        return

    raw_dir = config.DATA_RAW_DIR / "sancoes"
    raw_dir.mkdir(exist_ok=True)

    # As URLs de arquivo (CEIS_FILE_URL, CNEP_FILE_URL, PGFN_FILE_URL) devem
    # ser coladas manualmente via variável de ambiente — ver instruções em
    # config.py. Cada uma é validada antes do download para pegar erro cedo
    # caso ainda esteja com o placeholder ou aponte pra página, não arquivo.
    try:
        url_validation.validar_url_arquivo(config.CEIS_URL, "CEIS")
        ceis_path = _obter_csv(config.CEIS_URL, raw_dir / "ceis.csv")
        processar_ceis_cnep(ceis_path, "CEIS", cnpjs_validos)
    except (url_validation.UrlInvalidaError, FileNotFoundError) as e:
        print(f"[sanctions_ingest] Pulando CEIS: {e}")

    try:
        url_validation.validar_url_arquivo(config.CNEP_URL, "CNEP")
        cnep_path = _obter_csv(config.CNEP_URL, raw_dir / "cnep.csv")
        processar_ceis_cnep(cnep_path, "CNEP", cnpjs_validos)
    except (url_validation.UrlInvalidaError, FileNotFoundError) as e:
        print(f"[sanctions_ingest] Pulando CNEP: {e}")

    try:
        url_validation.validar_url_arquivo(config.PGFN_DIVIDA_ATIVA_URL, "PGFN Dívida Ativa")
        # Nome do destino segue a extensão real da URL — o dataset da PGFN
        # (confirmado em 21/07/2026) vem como .zip, não CSV único.
        extensao = Path(config.PGFN_DIVIDA_ATIVA_URL.split("?")[0]).suffix or ".csv"
        arquivo = _obter_csv(config.PGFN_DIVIDA_ATIVA_URL, raw_dir / f"divida_ativa{extensao}")
        caminhos_csv = _extrair_csvs_do_zip(arquivo) if arquivo.suffix.lower() == ".zip" else [arquivo]
        processar_divida_ativa(caminhos_csv, cnpjs_validos)
    except (url_validation.UrlInvalidaError, FileNotFoundError) as e:
        print(f"[sanctions_ingest] Pulando PGFN: {e}")


if __name__ == "__main__":
    executar()
