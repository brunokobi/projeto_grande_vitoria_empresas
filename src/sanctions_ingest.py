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


CGU_BASE = "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida"


def _baixar_cgu(fonte: str, destino_dir: Path, sufixo: str = None):
    """Baixa o arquivo mais recente de uma fonte da CGU (ceis/cnep/cepim/
    acordos-leniencia) direto do S3 de dados abertos (sem WAF). Tenta hoje e
    volta até 15 dias até achar um arquivo publicado. Retorna o caminho do zip
    ou None. `sufixo` cobre fontes cujo nome do arquivo difere de fonte.upper()
    (ex.: acordos-leniencia → 'AcordosLeniencia')."""
    import datetime
    sufixo = sufixo or fonte.upper()
    hoje = datetime.date.today()
    for i in range(16):
        d = (hoje - datetime.timedelta(days=i)).strftime("%Y%m%d")
        url = f"{CGU_BASE}/{fonte}/{d}_{sufixo}.zip"
        try:
            if requests.head(url, timeout=30).status_code == 200:
                destino = destino_dir / f"{fonte}.zip"
                print(f"[sanctions_ingest] Baixando {sufixo} de {d} ...")
                with requests.get(url, stream=True, timeout=300) as resp:
                    resp.raise_for_status()
                    with open(destino, "wb") as f:
                        for chunk in resp.iter_content(1024 * 1024):
                            f.write(chunk)
                return destino
        except requests.RequestException:
            continue
    return None


def processar_ceis_cnep(zip_path: Path, tipo: str, cnpjs_validos: set):
    """tipo: 'CEIS' ou 'CNEP'. Extrai o zip (CGU) e grava as sanções federais
    vinculadas aos CNPJs da base, com fundamentação legal e nº do processo."""
    total = 0
    with db_utils.get_conn() as conn:
        for csv_path in _extrair_csvs_do_zip(zip_path):
            df = pd.read_csv(csv_path, sep=";", encoding="latin-1", dtype=str)
            df.columns = [c.strip().strip('"') for c in df.columns]
            for _, row in df.iterrows():
                cnpj = matching.normalizar_cnpj(row.get("CPF OU CNPJ DO SANCIONADO", ""))
                if len(cnpj) != 14 or cnpj not in cnpjs_validos:
                    continue
                registro = {
                    "cnpj_empresa": cnpj,
                    "tipo": tipo,
                    "motivo": row.get("CATEGORIA DA SANÇÃO", ""),
                    "orgao_sancionador": row.get("ÓRGÃO SANCIONADOR", ""),
                    "data_inicio": row.get("DATA INÍCIO SANÇÃO", ""),
                    "data_fim": row.get("DATA FINAL SANÇÃO", ""),
                    "valor_multa": None,
                    "fundamentacao": row.get("FUNDAMENTAÇÃO LEGAL", ""),
                    "numero_processo": row.get("NÚMERO DO PROCESSO", ""),
                    "match_confianca": "direto",
                }
                db_utils.insert_generic(conn, "sancoes_administrativas", registro)
                total += 1
    print(f"[sanctions_ingest] {tipo}: {total} sanções federais vinculadas.")


def _limpar_tipo(conn, tipo: str):
    """Remove sanções de um tipo antes de reinserir — deixa a etapa idempotente
    (rodar de novo não duplica)."""
    conn.execute("DELETE FROM sancoes_administrativas WHERE tipo = ?", (tipo,))


def processar_cepim(zip_path: Path, cnpjs_validos: set):
    """CEPIM (CGU): entidades privadas impedidas de receber recursos/convênios
    federais. Grava na mesma tabela de sanções administrativas (tipo=CEPIM)."""
    total = 0
    with db_utils.get_conn() as conn:
        _limpar_tipo(conn, "CEPIM")
        for csv_path in _extrair_csvs_do_zip(zip_path):
            df = pd.read_csv(csv_path, sep=";", encoding="latin-1", dtype=str)
            df.columns = [c.strip().strip('"') for c in df.columns]
            for _, row in df.iterrows():
                cnpj = matching.normalizar_cnpj(row.get("CNPJ ENTIDADE", ""))
                if len(cnpj) != 14 or cnpj not in cnpjs_validos:
                    continue
                convenio = (row.get("NÚMERO CONVÊNIO") or "").strip()
                registro = {
                    "cnpj_empresa": cnpj,
                    "tipo": "CEPIM",
                    "motivo": row.get("MOTIVO DO IMPEDIMENTO", ""),
                    "orgao_sancionador": row.get("ÓRGÃO CONCEDENTE", ""),
                    "data_inicio": None,
                    "data_fim": None,
                    "valor_multa": None,
                    "fundamentacao": f"Convênio nº {convenio}" if convenio else "",
                    "numero_processo": convenio,
                    "match_confianca": "direto",
                }
                db_utils.insert_generic(conn, "sancoes_administrativas", registro)
                total += 1
    print(f"[sanctions_ingest] CEPIM: {total} impedimentos vinculados.")


def processar_leniencia(zip_path: Path, cnpjs_validos: set):
    """Acordos de Leniência (CGU): empresas que firmaram acordo com a União.
    Grava na tabela de sanções administrativas (tipo=LENIENCIA)."""
    total = 0
    with db_utils.get_conn() as conn:
        _limpar_tipo(conn, "LENIENCIA")
        for csv_path in _extrair_csvs_do_zip(zip_path):
            df = pd.read_csv(csv_path, sep=";", encoding="latin-1", dtype=str)
            df.columns = [c.strip().strip('"') for c in df.columns]
            # a coluna de situação vem com a grafia "LENIÊNICA" no arquivo da CGU
            col_sit = next((c for c in df.columns if c.startswith("SITUAÇÃO DO ACORDO")), None)
            for _, row in df.iterrows():
                cnpj = matching.normalizar_cnpj(row.get("CNPJ DO SANCIONADO", ""))
                if len(cnpj) != 14 or cnpj not in cnpjs_validos:
                    continue
                situacao = (row.get(col_sit) if col_sit else "") or ""
                registro = {
                    "cnpj_empresa": cnpj,
                    "tipo": "LENIENCIA",
                    "motivo": (f"Acordo de leniência — {situacao}").strip(" —"),
                    "orgao_sancionador": row.get("ÓRGÃO SANCIONADOR", ""),
                    "data_inicio": row.get("DATA DE INÍCIO DO ACORDO", ""),
                    "data_fim": row.get("DATA DE FIM DO ACORDO", ""),
                    "valor_multa": None,
                    "fundamentacao": (row.get("TERMOS DO ACORDO", "") or "")[:500],
                    "numero_processo": row.get("NÚMERO DO PROCESSO", ""),
                    "match_confianca": "direto",
                }
                db_utils.insert_generic(conn, "sancoes_administrativas", registro)
                total += 1
    print(f"[sanctions_ingest] Leniência: {total} acordos vinculados.")


# --- Lista Suja do trabalho escravo (MTE) -----------------------------------
# ATENÇÃO: o gov.br é hostil a acesso automatizado — WAF que responde 404/403
# de forma INTERMITENTE, páginas em JS e a URL do PDF muda a cada semestre.
# Por isso este resolvedor é defensivo: tenta URLs conhecidas com retries e,
# se falharem, raspa a página-seção atrás do link .pdf atual. Se um dia parar
# de funcionar, o ponto de conserto é só este bloco (e as URLs abaixo).
_UA_NAV = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")}
LISTA_SUJA_URLS = [
    "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/areas-de-atuacao/documentos-pdf/cadastro_de_empregadores.pdf",
    "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/areas-de-atuacao/cadastro_de_empregadores.pdf",
]
LISTA_SUJA_SECAO = ("https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/"
                    "areas-de-atuacao/combate-ao-trabalho-escravo-e-analogo-ao-de-escravo")


def _baixar_lista_suja(tentativas: int = 12):
    """Baixa o PDF do Cadastro de Empregadores (Lista Suja) do MTE. Retorna os
    bytes do PDF ou None. Lida com o 404/403 intermitente do WAF do gov.br via
    retries e, em último caso, descobre o link atual na página-seção."""
    import time
    import re as _re
    sess = requests.Session()
    sess.headers.update(_UA_NAV)

    def _get_pdf(url, n):
        for _ in range(n):
            try:
                r = sess.get(url, timeout=90)
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    return r.content
            except requests.RequestException:
                pass
            time.sleep(1.5)
        return None

    for url in LISTA_SUJA_URLS:
        pdf = _get_pdf(url, tentativas)
        if pdf:
            return pdf
    # fallback: raspar a página-seção pra achar o link .pdf atual do cadastro
    for _ in range(6):
        try:
            r = sess.get(LISTA_SUJA_SECAO, timeout=60)
            if r.status_code == 200:
                for l in _re.findall(r'href="([^"]+\.pdf[^"]*)"', r.text, _re.I):
                    if "empregador" in l.lower() or "cadastro_de_empregadores" in l.lower():
                        u = l if l.startswith("http") else "https://www.gov.br" + l
                        pdf = _get_pdf(u, 6)
                        if pdf:
                            return pdf
        except requests.RequestException:
            pass
        time.sleep(2)
    return None


def processar_lista_suja(pdf_bytes: bytes, cnpjs_validos: set):
    """Lista Suja do trabalho escravo (MTE): empregadores flagrados submetendo
    trabalhadores a condições análogas à escravidão. O arquivo é um PDF com
    tabela; extraímos com pdfplumber. Grava na tabela de sanções
    (tipo=TRABALHO_ESCRAVO) — aparece nos mesmos cards/filtros de sanção."""
    import io
    import re as _re
    import pdfplumber
    total = 0
    with db_utils.get_conn() as conn:
        _limpar_tipo(conn, "TRABALHO_ESCRAVO")
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
            for page in doc.pages:
                for tab in page.extract_tables():
                    for row in tab:
                        # linha de dado tem >=10 células e começa com ID numérico
                        if not row or len(row) < 10:
                            continue
                        if not (row[0] and str(row[0]).strip().isdigit()):
                            continue
                        cnpj = matching.normalizar_cnpj(row[4] or "")
                        if len(cnpj) != 14 or cnpj not in cnpjs_validos:
                            continue
                        empregador = (row[3] or "").replace("\n", " ").strip()
                        empregador = _re.sub(r"^[\d.]{8,}\s+", "", empregador)  # tira raiz do CNPJ do nome
                        trab = (row[6] or "").strip()
                        estab = (row[5] or "").replace("\n", " ").strip()
                        ano = (row[1] or "").replace("\n", " ").strip()
                        registro = {
                            "cnpj_empresa": cnpj,
                            "tipo": "TRABALHO_ESCRAVO",
                            "motivo": (f"Trabalho análogo à escravidão — {trab} trabalhador(es)").strip(" —"),
                            "orgao_sancionador": "MTE — Cadastro de Empregadores (Lista Suja)",
                            "data_inicio": (row[8] or "").strip(),
                            "data_fim": (row[9] or "").strip(),
                            "valor_multa": None,
                            "fundamentacao": (f"Estabelecimento: {estab} · Ano da ação fiscal: {ano} · "
                                              "Portaria Interministerial MTE/MDHC/MIR nº 18/2024"),
                            "numero_processo": "",
                            "match_confianca": "direto",
                        }
                        db_utils.insert_generic(conn, "sancoes_administrativas", registro)
                        total += 1
    print(f"[sanctions_ingest] Lista Suja (trabalho escravo): {total} vinculados.")


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
                        "tipo_tributo": row.get("RECEITA_PRINCIPAL", ""),
                        "numero_inscricao": row.get("NUMERO_INSCRICAO", ""),
                        "ajuizada": row.get("INDICADOR_AJUIZADO", ""),
                        "tipo_devedor": row.get("TIPO_DEVEDOR", ""),
                        "unidade_responsavel": row.get("UNIDADE_RESPONSAVEL", ""),
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

    # CEIS/CNEP (sanções federais): baixadas direto do S3 de dados abertos da
    # CGU (dadosabertos-download.cgu.gov.br) — sem WAF. _baixar_cgu acha o
    # arquivo publicado mais recente automaticamente. Não usa mais as URLs de
    # página do Portal da Transparência.
    for fonte, tipo in [("ceis", "CEIS"), ("cnep", "CNEP")]:
        try:
            zip_path = _baixar_cgu(fonte, raw_dir)
            if zip_path:
                processar_ceis_cnep(zip_path, tipo, cnpjs_validos)
            else:
                print(f"[sanctions_ingest] {tipo}: nenhum arquivo recente encontrado no S3 da CGU.")
        except Exception as e:
            print(f"[sanctions_ingest] Falha em {tipo}: {e}")

    # CEPIM (impedidos de receber recursos federais) e Acordos de Leniência —
    # mesma CGU/mesmo S3 de dados abertos. A leniência tem sufixo de arquivo
    # próprio ('AcordosLeniencia').
    try:
        zp = _baixar_cgu("cepim", raw_dir)
        if zp:
            processar_cepim(zp, cnpjs_validos)
        else:
            print("[sanctions_ingest] CEPIM: nenhum arquivo recente no S3 da CGU.")
    except Exception as e:
        print(f"[sanctions_ingest] Falha em CEPIM: {e}")

    try:
        zp = _baixar_cgu("acordos-leniencia", raw_dir, sufixo="AcordosLeniencia")
        if zp:
            processar_leniencia(zp, cnpjs_validos)
        else:
            print("[sanctions_ingest] Leniência: nenhum arquivo recente no S3 da CGU.")
    except Exception as e:
        print(f"[sanctions_ingest] Falha em Leniência: {e}")

    # Lista Suja do trabalho escravo (MTE) — PDF instável, ver _baixar_lista_suja
    try:
        pdf = _baixar_lista_suja()
        if pdf:
            processar_lista_suja(pdf, cnpjs_validos)
        else:
            print("[sanctions_ingest] Lista Suja: não consegui baixar o PDF do MTE "
                  "nesta execução (WAF/URL instável). Rode a etapa de novo mais tarde.")
    except Exception as e:
        print(f"[sanctions_ingest] Falha na Lista Suja: {e}")

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
