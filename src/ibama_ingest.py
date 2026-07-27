"""
Ingestão de autos de infração ambiental do IBAMA (dados abertos).

O IBAMA disponibiliza o dataset de fiscalização/autos de infração em CSV.
A coluna de CPF/CNPJ do autuado costuma se chamar "CPF_CNPJ_INFRATOR" ou
similar — sempre inspecionar o cabeçalho real antes de rodar em produção,
pois o layout já mudou entre versões do dataset.
"""
import zipfile
from pathlib import Path

import requests
import pandas as pd

import config
from src import db_utils, matching, url_validation


def _baixar_csv(url: str, destino: Path) -> Path:
    if destino.exists():
        print(f"[ibama_ingest] {destino.name} já baixado, pulando.")
        return destino
    print(f"[ibama_ingest] Baixando {url} ...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    destino.write_bytes(resp.content)
    return destino


def _obter_csv(origem: str, destino: Path) -> Path:
    """Aceita URL http(s) ou caminho de arquivo local já baixado manualmente."""
    if origem.lower().startswith("http"):
        return _baixar_csv(origem, destino)
    caminho_local = Path(origem).expanduser()
    if not caminho_local.exists():
        raise FileNotFoundError(
            f"Arquivo local não encontrado: {caminho_local}. Confira o caminho no .env."
        )
    print(f"[ibama_ingest] Usando arquivo local {caminho_local}")
    return caminho_local


def _to_float(v):
    """Valor monetário -> float. Aceita BR (1.234,56) e US (1234.56)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")   # ponto = milhar
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _extrair_csvs_do_zip(zip_path: Path) -> list:
    """
    O dataset atual do IBAMA (confirmado em 21/07/2026) é um ZIP com um CSV
    por ano (ex.: auto_infracao_2026.csv), não um CSV único — extrai todos
    para processar em conjunto.
    """
    extract_dir = zip_path.parent / f"{zip_path.stem}_extraido"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        nomes_csv = [n for n in z.namelist() if n.lower().endswith(".csv")]
        z.extractall(extract_dir, members=nomes_csv)
    return [extract_dir / n for n in nomes_csv]


def processar_autos_infracao(caminhos_csv: list, cnpjs_validos: set):
    total = 0
    with db_utils.get_conn() as conn:
        for caminho_csv in caminhos_csv:
            # O dataset do IBAMA (confirmado em 21/07/2026) é UTF-8, diferente
            # das outras fontes (RF/Portal da Transparência), que usam latin-1.
            reader = pd.read_csv(
                caminho_csv, sep=";", encoding="utf-8", dtype=str, chunksize=100_000
            )
            for chunk in reader:
                col_doc = next(
                    (c for c in chunk.columns if "CPF" in c.upper() or "CNPJ" in c.upper()),
                    None,
                )
                if col_doc is None:
                    raise RuntimeError(
                        f"Coluna de CNPJ não encontrada em {caminho_csv.name} — "
                        "inspecionar o cabeçalho e ajustar o nome da coluna."
                    )
                chunk["cnpj_norm"] = chunk[col_doc].fillna("").apply(matching.normalizar_cnpj)
                filtrado = chunk[chunk["cnpj_norm"].isin(cnpjs_validos)]
                for _, row in filtrado.iterrows():
                    registro = {
                        "cnpj_empresa": row["cnpj_norm"],
                        "orgao": "IBAMA",
                        "tipo_infracao": row.get("DES_INFRACAO") or row.get("TIPO_INFRACAO", ""),
                        "valor_multa": _to_float(row.get("VAL_AUTO_INFRACAO")),
                        "status": row.get("DS_SIT_AUTO_AIE", ""),
                        "data_auto": row.get("DAT_HORA_AUTO_INFRACAO", ""),
                        "gravidade": row.get("GRAVIDADE_INFRACAO", ""),
                        "tipo_multa": row.get("TIPO_MULTA", ""),
                        "numero_auto": row.get("NUM_AUTO_INFRACAO", ""),
                        "municipio_infracao": row.get("MUNICIPIO", ""),
                        "uf_infracao": row.get("UF", ""),
                        "enquadramento": row.get("DS_ENQUADRAMENTO_ADMINISTRATIVO", ""),
                        "match_confianca": "direto",
                    }
                    db_utils.insert_generic(conn, "infracoes_ambientais", registro)
                    total += 1
    print(f"[ibama_ingest] {total} infrações ambientais vinculadas.")


def executar():
    with db_utils.get_conn() as conn:
        cnpjs_validos = {r["cnpj"] for r in db_utils.listar_cnpjs(conn)}

    if not cnpjs_validos:
        print("[ibama_ingest] Nenhum CNPJ carregado ainda — rode cnpj_ingest primeiro.")
        return

    raw_dir = config.DATA_RAW_DIR / "ibama"
    raw_dir.mkdir(exist_ok=True)

    # A URL de arquivo (IBAMA_FILE_URL) deve ser colada manualmente via
    # variável de ambiente — ver instruções em config.py.
    try:
        url_validation.validar_url_arquivo(config.IBAMA_AUTOS_INFRACAO_URL, "IBAMA")
        # Nome do destino segue a extensão real da URL (.zip ou .csv) — o
        # dataset atual do IBAMA é um .zip com vários CSVs dentro, não um
        # CSV único.
        extensao = Path(config.IBAMA_AUTOS_INFRACAO_URL.split("?")[0]).suffix or ".csv"
        arquivo = _obter_csv(config.IBAMA_AUTOS_INFRACAO_URL, raw_dir / f"autos_infracao{extensao}")
        if arquivo.suffix.lower() == ".zip":
            caminhos_csv = _extrair_csvs_do_zip(arquivo)
        else:
            caminhos_csv = [arquivo]
        processar_autos_infracao(caminhos_csv, cnpjs_validos)
    except (url_validation.UrlInvalidaError, FileNotFoundError) as e:
        print(f"[ibama_ingest] Pulando IBAMA: {e}")


if __name__ == "__main__":
    executar()
