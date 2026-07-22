"""
Ingestão de dados da JUCEES (Junta Comercial do Estado do Espírito Santo)
via portal de dados abertos do Governo do ES (dados.es.gov.br, CKAN).

Fonte: https://dados.es.gov.br/dataset/empresas
Colunas confirmadas no dicionário de dados oficial (dataset "Relatório
Empresas Ativas com cadastro completo"):
    NOME EMPRESA, NOME FANTASIA, CNPJ, NIRE, CONSTITUICAO, LOGRADOURO,
    NUMERO, COMPLEMENTO, BAIRRO, MUNICIPIO, CEP, COD NATUREZA JURIDICA,
    NATUREZA JURIDICA, ATIVIDADE PRINCIPAL

LIMITAÇÃO: este dataset cobre apenas empresas com natureza jurídica
'Sociedade Empresária' do ramo de serviços e comércio — não é o universo
completo (não inclui MEI, Empresário Individual, etc.). Por isso é
tratado como COMPLEMENTO à base da Receita Federal, não substituto: só
adiciona NIRE, data de constituição e natureza jurídica descritiva para
os CNPJs que também aparecem aqui.

O arquivo é grande (~56 MiB na última checagem), lido em chunks.
"""
import unicodedata
from pathlib import Path

import requests
import pandas as pd

import config
from src import db_utils, matching


def _sem_acento(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper()


def _baixar_csv(url: str, destino: Path) -> Path:
    if destino.exists():
        print(f"[jucees_ingest] {destino.name} já baixado, pulando.")
        return destino
    print(f"[jucees_ingest] Baixando {url} ...")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    return destino


def processar(caminho_csv: Path, cnpjs_validos: set, chunk_size: int = 50_000):
    """
    Filtra o CSV da JUCEES pelo recorte geográfico da Grande Vitória e pelos
    CNPJs já carregados no banco (interseção com a base da Receita Federal),
    gravando o complemento (NIRE, constituição, natureza jurídica) na tabela
    `registros_jucees`.
    """
    total_grande_vitoria = 0
    total_vinculado = 0

    reader = pd.read_csv(
        caminho_csv, encoding="utf-8-sig", dtype=str, chunksize=chunk_size,
        sep=",",  # dump do CKAN via datastore geralmente vem separado por vírgula
    )

    with db_utils.get_conn() as conn:
        for chunk in reader:
            # Normaliza nomes de coluna (o dump do CKAN às vezes inclui uma
            # coluna extra "_id" no início — não interfere no resto).
            chunk.columns = [c.strip().upper() for c in chunk.columns]

            if "MUNICIPIO" not in chunk.columns or "CNPJ" not in chunk.columns:
                raise RuntimeError(
                    "Colunas MUNICIPIO/CNPJ não encontradas no CSV da JUCEES — "
                    "o layout pode ter mudado. Colunas encontradas: "
                    f"{list(chunk.columns)}"
                )

            chunk["municipio_norm"] = chunk["MUNICIPIO"].fillna("").apply(_sem_acento)
            chunk["cnpj_norm"] = chunk["CNPJ"].fillna("").apply(matching.normalizar_cnpj)

            filtro_geo = chunk["municipio_norm"].isin(config.MUNICIPIOS_GRANDE_VITORIA)
            filtrado_geo = chunk[filtro_geo]
            total_grande_vitoria += len(filtrado_geo)

            filtrado = filtrado_geo[filtrado_geo["cnpj_norm"].isin(cnpjs_validos)]
            total_vinculado += len(filtrado)

            for _, row in filtrado.iterrows():
                registro = {
                    "cnpj_empresa": row["cnpj_norm"],
                    "nire": row.get("NIRE"),
                    "data_constituicao": row.get("CONSTITUICAO"),
                    "nome_fantasia_jucees": row.get("NOME FANTASIA"),
                    "cod_natureza_juridica": row.get("COD NATUREZA JURIDICA"),
                    "natureza_juridica": row.get("NATUREZA JURIDICA"),
                    "atividade_principal_jucees": row.get("ATIVIDADE PRINCIPAL"),
                    "data_atualizacao": pd.Timestamp.now().isoformat(),
                }
                cols = ", ".join(registro.keys())
                placeholders = ", ".join(["?"] * len(registro))
                updates = ", ".join(f"{k}=excluded.{k}" for k in registro if k != "cnpj_empresa")
                conn.execute(
                    f"""INSERT INTO registros_jucees ({cols}) VALUES ({placeholders})
                        ON CONFLICT(cnpj_empresa) DO UPDATE SET {updates}""",
                    list(registro.values()),
                )

    print(
        f"[jucees_ingest] {total_grande_vitoria} registros da JUCEES na Grande "
        f"Vitória encontrados; {total_vinculado} vinculados a CNPJs já "
        f"carregados da Receita Federal."
    )


def executar():
    with db_utils.get_conn() as conn:
        cnpjs_validos = {r["cnpj"] for r in db_utils.listar_cnpjs(conn)}

    if not cnpjs_validos:
        print("[jucees_ingest] Nenhum CNPJ carregado ainda — rode cnpj_ingest primeiro.")
        return

    raw_dir = config.DATA_RAW_DIR / "jucees"
    raw_dir.mkdir(exist_ok=True)

    csv_path = _baixar_csv(config.JUCEES_DATASTORE_DUMP_URL, raw_dir / "jucees_empresas.csv")
    processar(csv_path, cnpjs_validos)


if __name__ == "__main__":
    executar()
