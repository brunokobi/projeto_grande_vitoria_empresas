"""
Exportação final: junta a tabela mestre `empresas` com agregados de cada
tabela satélite (sócios, processos, sanções, infrações ambientais, dívida
ativa, enriquecimento Places) em UM dataset — uma linha por empresa.

Colunas de detalhe (ex.: lista de processos) ficam disponíveis à parte,
em abas/arquivos separados, pra quem precisar do detalhe completo sem
poluir a visão consolidada.

Gera dois formatos: CSV (mais leve, universal) e XLSX (com abas
separadas para o resumo e o detalhe de cada categoria).
"""
from pathlib import Path

import pandas as pd

import config

OUTPUT_DIR = config.BASE_DIR / "output"


def _query_df(conn, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn)


def gerar_dataset_consolidado():
    import sqlite3
    OUTPUT_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(config.DB_PATH)

    empresas = _query_df(conn, "SELECT * FROM empresas")
    jucees = _query_df(conn, "SELECT * FROM registros_jucees")
    socios = _query_df(conn, "SELECT * FROM socios")
    processos = _query_df(conn, "SELECT * FROM processos_judiciais")
    sancoes = _query_df(conn, "SELECT * FROM sancoes_administrativas")
    ambiental = _query_df(conn, "SELECT * FROM infracoes_ambientais")
    dividas = _query_df(conn, "SELECT * FROM dividas_ativas")
    places = _query_df(conn, "SELECT * FROM enriquecimento_places")

    conn.close()

    if empresas.empty:
        print("[export_dataset] Nenhuma empresa no banco ainda — rode as etapas de ingestão primeiro.")
        return

    # --- Agregados por CNPJ, pra virar colunas na tabela consolidada -------
    def agrega_contagem(df, coluna_cnpj, nome_saida):
        if df.empty:
            return pd.DataFrame(columns=["cnpj", nome_saida])
        g = df.groupby(coluna_cnpj).size().reset_index(name=nome_saida)
        return g.rename(columns={coluna_cnpj: "cnpj"})

    def agrega_soma(df, coluna_cnpj, coluna_valor, nome_saida):
        if df.empty:
            return pd.DataFrame(columns=["cnpj", nome_saida])
        g = df.groupby(coluna_cnpj)[coluna_valor].sum(min_count=1).reset_index(name=nome_saida)
        return g.rename(columns={coluna_cnpj: "cnpj"})

    qtd_socios = agrega_contagem(socios, "cnpj_empresa", "qtd_socios")
    qtd_processos = agrega_contagem(processos, "cnpj_empresa", "qtd_processos_judiciais")
    qtd_sancoes = agrega_contagem(sancoes, "cnpj_empresa", "qtd_sancoes_administrativas")
    qtd_ambiental = agrega_contagem(ambiental, "cnpj_empresa", "qtd_infracoes_ambientais")
    qtd_dividas = agrega_contagem(dividas, "cnpj_empresa", "qtd_registros_divida_ativa")
    soma_dividas = agrega_soma(dividas, "cnpj_empresa", "valor", "valor_total_divida_ativa")

    consolidado = empresas.copy()

    # JUCEES é 1:1 por CNPJ (não precisa agregação como as outras tabelas
    # satélite) — só nem toda empresa vai ter registro aqui (dataset cobre
    # só 'Sociedade Empresária' do ramo de serviços/comércio).
    if not jucees.empty:
        consolidado = consolidado.merge(
            jucees.rename(columns={"cnpj_empresa": "cnpj"}), on="cnpj", how="left"
        )

    for agregado in (qtd_socios, qtd_processos, qtd_sancoes, qtd_ambiental, qtd_dividas, soma_dividas):
        consolidado = consolidado.merge(agregado, on="cnpj", how="left")

    if not places.empty:
        consolidado = consolidado.merge(
            places.rename(columns={"cnpj_empresa": "cnpj"}), on="cnpj", how="left"
        )

    # Preenche contagens com 0 (empresa sem nenhum registro na categoria)
    for col in [
        "qtd_socios", "qtd_processos_judiciais", "qtd_sancoes_administrativas",
        "qtd_infracoes_ambientais", "qtd_registros_divida_ativa",
    ]:
        if col in consolidado.columns:
            consolidado[col] = consolidado[col].fillna(0).astype(int)

    # Coluna de sinalização rápida, útil pra triagem/prospecção
    consolidado["tem_pendencia_juridica_ou_fiscal"] = (
        (consolidado.get("qtd_processos_judiciais", 0) > 0)
        | (consolidado.get("qtd_sancoes_administrativas", 0) > 0)
        | (consolidado.get("qtd_infracoes_ambientais", 0) > 0)
        | (consolidado.get("qtd_registros_divida_ativa", 0) > 0)
    )

    # --- Grava saídas -------------------------------------------------------
    csv_path = OUTPUT_DIR / "empresas_grande_vitoria_consolidado.csv"
    consolidado.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[export_dataset] CSV consolidado gravado em {csv_path} ({len(consolidado)} empresas)")

    xlsx_path = OUTPUT_DIR / "empresas_grande_vitoria_dataset.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        consolidado.to_excel(writer, sheet_name="Consolidado", index=False)
        if not jucees.empty:
            jucees.to_excel(writer, sheet_name="Jucees (detalhe)", index=False)
        if not socios.empty:
            socios.to_excel(writer, sheet_name="Socios (detalhe)", index=False)
        if not processos.empty:
            processos.to_excel(writer, sheet_name="Processos (detalhe)", index=False)
        if not sancoes.empty:
            sancoes.to_excel(writer, sheet_name="Sancoes (detalhe)", index=False)
        if not ambiental.empty:
            ambiental.to_excel(writer, sheet_name="Ambiental (detalhe)", index=False)
        if not dividas.empty:
            dividas.to_excel(writer, sheet_name="Divida Ativa (detalhe)", index=False)
    print(f"[export_dataset] XLSX com abas gravado em {xlsx_path}")


if __name__ == "__main__":
    gerar_dataset_consolidado()
