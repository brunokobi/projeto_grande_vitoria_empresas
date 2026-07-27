"""
Ingestão de sócios (quadro societário) da base de CNPJ da Receita Federal.

Baixa os arquivos Socios*.zip do mesmo mês, filtra pelos CNPJs já carregados
na base (recorte Grande Vitória) e grava na tabela `socios`. Retomável por
arquivo (checkpoint) e commit por arquivo — durável a quedas, sem duplicar.

Dados por sócio (públicos, como vêm da RF): nome, CPF já MASCARADO (LGPD),
código de qualificação, data de entrada e faixa etária.
"""
from pathlib import Path

import pandas as pd

import config
from src import cnpj_ingest, db_utils, checkpoint

CHECKPOINT = "socios_arquivos_processados"


def executar():
    # Mapa cnpj_basico -> [CNPJs completos] das empresas já na base.
    with db_utils.get_conn() as conn:
        cnpjs = [r["cnpj"] for r in conn.execute("SELECT cnpj FROM empresas")]
    if not cnpjs:
        print("[socios_ingest] Nenhuma empresa na base — rode cnpj primeiro.")
        return
    basico_map = {}
    for c in cnpjs:
        basico_map.setdefault(c[:8], []).append(c)
    basicos = set(basico_map)
    print(f"[socios_ingest] {len(basicos)} CNPJs básicos na base.")

    auth = cnpj_ingest._resolver_webdav_auth()
    pasta = cnpj_ingest.resolver_pasta_mes_atual(auth)
    socios_urls = cnpj_ingest._listar_arquivos(pasta, "Socios", auth)
    if not socios_urls:
        print("[socios_ingest] Nenhum arquivo Socios encontrado na pasta do mês.")
        return

    zips_dir = config.DATA_RAW_DIR / "zips"
    zips_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = config.DATA_RAW_DIR / "extracted"
    extract_dir.mkdir(exist_ok=True)

    processados = checkpoint.carregar(CHECKPOINT)
    total = 0
    for caminho in socios_urls:
        nome = Path(caminho).name
        if nome in processados:
            print(f"[socios_ingest] {nome} já processado, pulando.")
            continue

        destino = zips_dir / nome
        cnpj_ingest.baixar_arquivo(caminho, destino, auth)
        csv_paths = cnpj_ingest._extrair_csv_do_zip(destino, extract_dir)

        arq_total = 0
        with db_utils.get_conn() as conn:
            for csv_path in csv_paths:
                reader = pd.read_csv(
                    csv_path, sep=";", header=None, names=cnpj_ingest.HEADERS_SOCIOS,
                    encoding="latin-1", dtype=str, chunksize=200_000,
                )
                for chunk in reader:
                    filtrado = chunk[chunk["cnpj_basico"].isin(basicos)]
                    registros = []
                    for _, row in filtrado.iterrows():
                        for cnpj in basico_map.get(row["cnpj_basico"], []):
                            registros.append((
                                cnpj, row.get("nome_socio"),
                                row.get("cpf_cnpj_socio"), row.get("qualificacao_socio"),
                                row.get("data_entrada"), row.get("faixa_etaria"),
                            ))
                    if registros:
                        conn.executemany(
                            "INSERT INTO socios (cnpj_empresa, nome_socio, cpf_parcial, "
                            "qualificacao, data_entrada, faixa_etaria) VALUES (?, ?, ?, ?, ?, ?)",
                            registros,
                        )
                        arq_total += len(registros)
        checkpoint.marcar_processado(CHECKPOINT, nome)
        total += arq_total
        print(f"[socios_ingest] {nome}: {arq_total} sócios vinculados (total: {total}).")

    print(f"[socios_ingest] {total} sócios vinculados nesta execução.")


if __name__ == "__main__":
    executar()
