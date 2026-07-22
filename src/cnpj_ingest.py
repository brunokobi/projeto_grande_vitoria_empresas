"""
Ingestão da base pública de CNPJ (Receita Federal).

Fluxo:
  1. Resolve a pasta do mês mais recente no índice da RF.
  2. Baixa os arquivos Empresas*.zip, Estabelecimentos*.zip, Socios*.zip,
     Simples.zip e Municipios.zip.
  3. Extrai e lê cada CSV em chunks (arquivos completos passam de 1GB).
  4. Filtra Estabelecimentos por UF='ES' + município em MUNICIPIOS_GRANDE_VITORIA.
  5. Junta com Empresas (razão social, capital, porte), Simples
     (regime tributário) e Socios.
  6. Grava tudo já normalizado nas tabelas `empresas` e `socios` do SQLite.

Observação importante sobre o formato:
  Os arquivos da RF são CSV separados por ';', sem cabeçalho, encoding
  latin-1. O layout de colunas é documentado no arquivo
  "Layout Dados Abertos CNPJ" publicado junto com os dados. As posições
  usadas abaixo seguem esse layout oficial (posição 0-based).
"""
import re
import zipfile
import unicodedata
from pathlib import Path
from urllib.parse import unquote

import requests
import pandas as pd

import config
from src import db_utils

HEADERS_EMPRESAS = [
    "cnpj_basico", "razao_social", "natureza_juridica",
    "qualificacao_responsavel", "capital_social", "porte", "ente_federativo",
]
HEADERS_ESTABELECIMENTOS = [
    "cnpj_basico", "cnpj_ordem", "cnpj_dv", "identificador_matriz_filial",
    "nome_fantasia", "situacao_cadastral", "data_situacao_cadastral",
    "motivo_situacao_cadastral", "nome_cidade_exterior", "pais",
    "data_inicio_atividade", "cnae_principal", "cnae_secundarios",
    "tipo_logradouro", "logradouro", "numero", "complemento", "bairro",
    "cep", "uf", "municipio", "ddd1", "telefone1", "ddd2", "telefone2",
    "ddd_fax", "fax", "email", "situacao_especial", "data_situacao_especial",
]
HEADERS_SOCIOS = [
    "cnpj_basico", "identificador_socio", "nome_socio", "cpf_cnpj_socio",
    "qualificacao_socio", "data_entrada", "pais", "cpf_representante",
    "nome_representante", "qualificacao_representante", "faixa_etaria",
]
HEADERS_SIMPLES = [
    "cnpj_basico", "opcao_simples", "data_opcao_simples", "data_exclusao_simples",
    "opcao_mei", "data_opcao_mei", "data_exclusao_mei",
]
HEADERS_MUNICIPIOS = ["codigo_municipio", "nome_municipio"]


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper()


def _resolver_webdav_auth() -> tuple:
    """
    Resolve o token do link de compartilhamento Nextcloud da RF seguindo o
    redirect da URL raiz, em vez de fixar o token (evita quebrar se a RF
    recriar o compartilhamento). O WebDAV público do Nextcloud aceita o
    token como usuário e senha vazia (Basic Auth).
    """
    resp = requests.get(config.RFB_ROOT_URL, allow_redirects=False, timeout=30)
    location = resp.headers.get("Location", "")
    m = re.search(r"/s/([A-Za-z0-9]+)", location)
    if not m:
        raise RuntimeError(
            f"Não foi possível localizar o token do compartilhamento Nextcloud "
            f"da RF a partir do redirect de {config.RFB_ROOT_URL!r} "
            f"(Location recebido: {location!r}). O site pode ter mudado de "
            f"estrutura de novo — inspecionar manualmente."
        )
    return (m.group(1), "")


def _webdav_listar(caminho: str, auth: tuple) -> list:
    """Lista os nomes dos itens dentro de `caminho` via PROPFIND (Depth: 1)."""
    url = config.RFB_WEBDAV_BASE_URL + caminho
    resp = requests.request(
        "PROPFIND", url, auth=auth, headers={"Depth": "1"}, timeout=60
    )
    resp.raise_for_status()
    hrefs = re.findall(r"<d:href>([^<]+)</d:href>", resp.text)
    # O primeiro <d:href> é o próprio `caminho` consultado — descarta.
    return [unquote(h.rstrip("/").rsplit("/", 1)[-1]) for h in hrefs[1:]]


def resolver_pasta_mes_atual(auth: tuple) -> str:
    """Retorna o caminho WebDAV (relativo) da pasta do mês mais recente,
    ex.: 'Dados/Cadastros/CNPJ/2026-07/'."""
    nomes = _webdav_listar(config.RFB_CNPJ_WEBDAV_PATH + "/", auth)
    pastas = [n for n in nomes if re.match(r"^\d{4}-\d{2}$", n)]
    if not pastas:
        raise RuntimeError(
            f"Não foi possível localizar pastas mensais em "
            f"{config.RFB_CNPJ_WEBDAV_PATH} — o layout da RF pode ter mudado."
        )
    pasta_mais_recente = sorted(pastas)[-1]
    return f"{config.RFB_CNPJ_WEBDAV_PATH}/{pasta_mais_recente}/"


def _listar_arquivos(pasta_webdav: str, prefixo: str, auth: tuple) -> list:
    nomes = _webdav_listar(pasta_webdav, auth)
    return [
        pasta_webdav + n for n in nomes
        if n.startswith(prefixo) and n.endswith(".zip")
    ]


def baixar_arquivo(caminho_webdav: str, destino: Path, auth: tuple, tentativas: int = 3):
    """
    Baixa para um arquivo temporário e só renomeia para o nome final ao
    concluir com sucesso — evita que uma queda no meio do download (comum
    em arquivos de centenas de MB) deixe um arquivo parcial que seria
    tratado como "já baixado" numa execução seguinte. Reexecuta em caso de
    erro de rede transitório (timeout, conexão perdida).
    """
    if destino.exists():
        print(f"[cnpj_ingest] {destino.name} já baixado, pulando.")
        return
    url = config.RFB_WEBDAV_BASE_URL + caminho_webdav
    tmp = destino.with_name(destino.name + ".parcial")
    for tentativa in range(1, tentativas + 1):
        try:
            print(f"[cnpj_ingest] Baixando {url} (tentativa {tentativa}/{tentativas}) ...")
            with requests.get(url, auth=auth, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        f.write(chunk)
            tmp.rename(destino)
            return
        except requests.exceptions.RequestException as e:
            print(f"[cnpj_ingest] Erro baixando {destino.name}: {e}")
            if tentativa == tentativas:
                tmp.unlink(missing_ok=True)
                raise
    tmp.unlink(missing_ok=True)


def _extrair_csv_do_zip(zip_path: Path, extract_dir: Path) -> list:
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)
        return [extract_dir / n for n in z.namelist()]


def resolver_municipios_alvo(pasta_webdav: str, auth: tuple, zips_dir: Path) -> dict:
    """
    A coluna 'municipio' do arquivo de Estabelecimentos NÃO traz o nome da
    cidade — traz um código interno da Receita Federal (diferente do
    código IBGE de 7 dígitos), só resolvido através do arquivo
    Municipios.csv publicado junto no mesmo mês. Baixa esse arquivo e
    retorna {codigo: nome} apenas para os municípios da Grande Vitória
    (config.MUNICIPIOS_GRANDE_VITORIA).
    """
    urls = _listar_arquivos(pasta_webdav, "Municipios", auth)
    if not urls:
        raise RuntimeError(
            "Não foi possível localizar Municipios.zip na pasta do mês — "
            "necessário para resolver os códigos de município."
        )
    destino = zips_dir / Path(urls[0]).name
    baixar_arquivo(urls[0], destino, auth)

    extract_dir = config.DATA_RAW_DIR / "extracted"
    extract_dir.mkdir(exist_ok=True)
    csv_paths = _extrair_csv_do_zip(destino, extract_dir)

    df = pd.read_csv(
        csv_paths[0], sep=";", header=None, names=HEADERS_MUNICIPIOS,
        encoding="latin-1", dtype=str,
    )
    df["nome_norm"] = df["nome_municipio"].fillna("").apply(_sem_acento)
    alvo = df[df["nome_norm"].isin(config.MUNICIPIOS_GRANDE_VITORIA)]
    mapa = dict(zip(alvo["codigo_municipio"], alvo["nome_norm"]))
    if not mapa:
        raise RuntimeError(
            "Nenhum código de município da Grande Vitória encontrado em "
            "Municipios.csv — o layout pode ter mudado, inspecionar manualmente."
        )
    return mapa


def processar_estabelecimentos_e_empresas(
    empresas_zip_paths: list, estabelecimentos_zip_paths: list,
    simples_zip_path: Path, municipios_alvo: dict, chunk_size: int = 200_000,
):
    """
    Processa os arquivos em chunks, filtra pelo recorte geográfico e grava
    no SQLite. Feito em duas passagens porque Estabelecimentos define QUAIS
    cnpj_basico interessam (filtro geográfico); Empresas e Simples só
    completam colunas para esses CNPJs.

    municipios_alvo: {codigo_municipio_rf: nome_municipio}, resolvido via
    resolver_municipios_alvo — a coluna 'municipio' do CSV é esse código,
    não o nome da cidade.
    """
    extract_dir = config.DATA_RAW_DIR / "extracted"
    extract_dir.mkdir(exist_ok=True)

    # --- Passagem 1: Estabelecimentos -> filtra pelo município ------------
    cnpjs_basicos_alvo = set()
    linhas_filtradas = []

    for zip_path in estabelecimentos_zip_paths:
        csv_paths = _extrair_csv_do_zip(zip_path, extract_dir)
        for csv_path in csv_paths:
            reader = pd.read_csv(
                csv_path, sep=";", header=None, names=HEADERS_ESTABELECIMENTOS,
                encoding="latin-1", dtype=str, chunksize=chunk_size,
            )
            for chunk in reader:
                filtro = (
                    (chunk["uf"] == config.UF_ALVO)
                    & (chunk["municipio"].isin(municipios_alvo.keys()))
                    & (chunk["situacao_cadastral"] == "02")  # 02 = ATIVA no layout RF
                )
                filtrado = chunk[filtro]
                if not filtrado.empty:
                    cnpjs_basicos_alvo.update(filtrado["cnpj_basico"].tolist())
                    linhas_filtradas.append(filtrado)
            print(f"[cnpj_ingest] {csv_path.name}: {len(cnpjs_basicos_alvo)} CNPJs básicos acumulados.")

    if not linhas_filtradas:
        print("[cnpj_ingest] Nenhum estabelecimento encontrado no recorte geográfico.")
        return

    df_estabelecimentos = pd.concat(linhas_filtradas, ignore_index=True)

    # --- Passagem 2: Empresas (razão social, capital, porte) --------------
    dfs_empresas = []
    for zip_path in empresas_zip_paths:
        csv_paths = _extrair_csv_do_zip(zip_path, extract_dir)
        for csv_path in csv_paths:
            reader = pd.read_csv(
                csv_path, sep=";", header=None, names=HEADERS_EMPRESAS,
                encoding="latin-1", dtype=str, chunksize=chunk_size,
            )
            for chunk in reader:
                filtrado = chunk[chunk["cnpj_basico"].isin(cnpjs_basicos_alvo)]
                if not filtrado.empty:
                    dfs_empresas.append(filtrado)
    df_empresas = pd.concat(dfs_empresas, ignore_index=True) if dfs_empresas else pd.DataFrame(columns=HEADERS_EMPRESAS)
    df_empresas = df_empresas.drop_duplicates(subset="cnpj_basico", keep="first")

    # --- Simples Nacional / MEI --------------------------------------------
    df_simples = pd.DataFrame()
    if simples_zip_path and simples_zip_path.exists():
        csv_paths = _extrair_csv_do_zip(simples_zip_path, extract_dir)
        dfs_simples = []
        for csv_path in csv_paths:
            reader = pd.read_csv(
                csv_path, sep=";", header=None, names=HEADERS_SIMPLES,
                encoding="latin-1", dtype=str, chunksize=chunk_size,
            )
            for chunk in reader:
                filtrado = chunk[chunk["cnpj_basico"].isin(cnpjs_basicos_alvo)]
                if not filtrado.empty:
                    dfs_simples.append(filtrado)
        df_simples = pd.concat(dfs_simples, ignore_index=True) if dfs_simples else pd.DataFrame(columns=HEADERS_SIMPLES)
    df_simples = df_simples.drop_duplicates(subset="cnpj_basico", keep="first")

    # --- Junta tudo via merge (evita filtro linha a linha O(n×m)) ----------
    df = df_estabelecimentos.merge(
        df_empresas[["cnpj_basico", "razao_social", "capital_social", "porte"]],
        on="cnpj_basico", how="left",
    ).merge(
        df_simples[["cnpj_basico", "opcao_mei", "opcao_simples"]],
        on="cnpj_basico", how="left",
    )

    df["cnpj"] = df["cnpj_basico"] + df["cnpj_ordem"] + df["cnpj_dv"]
    # Grava o NOME do município (não o código bruto da RF) — geo_enrich.py
    # usa essa coluna para montar o endereço de geocodificação.
    df["municipio"] = df["municipio"].map(municipios_alvo)
    df["capital_social"] = df["capital_social"].apply(_to_float)
    df["telefone"] = df.apply(
        lambda r: _monta_telefone(r.get("ddd1"), r.get("telefone1")), axis=1
    )
    df["regime_tributario"] = "Normal"
    df.loc[df["opcao_simples"] == "S", "regime_tributario"] = "Simples Nacional"
    df.loc[df["opcao_mei"] == "S", "regime_tributario"] = "MEI"  # MEI tem prioridade
    df["data_ultima_atualizacao"] = pd.Timestamp.now().isoformat()

    db_utils.init_db()
    with db_utils.get_conn() as conn:
        for _, row in df.iterrows():
            empresa_dict = {
                "cnpj": row["cnpj"],
                "razao_social": row.get("razao_social"),
                "nome_fantasia": row.get("nome_fantasia"),
                "cnae_principal": row.get("cnae_principal"),
                "cnae_secundarios": row.get("cnae_secundarios"),
                "situacao_cadastral": row.get("situacao_cadastral"),
                "data_situacao": row.get("data_situacao_cadastral"),
                "porte": row.get("porte"),
                "capital_social": row.get("capital_social"),
                "municipio": row.get("municipio"),
                "uf": row.get("uf"),
                "logradouro": row.get("logradouro"),
                "numero": row.get("numero"),
                "bairro": row.get("bairro"),
                "cep": row.get("cep"),
                "telefone": row.get("telefone"),
                "email": row.get("email"),
                "regime_tributario": row.get("regime_tributario"),
                "data_ultima_atualizacao": row.get("data_ultima_atualizacao"),
            }
            db_utils.upsert_empresa(conn, empresa_dict)
    print(f"[cnpj_ingest] {len(df)} empresas carregadas no banco.")


def _to_float(valor):
    if valor is None:
        return None
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return None


def _monta_telefone(ddd, numero):
    if ddd and numero:
        return f"({ddd}) {numero}"
    return None


def executar():
    """Ponto de entrada do módulo — orquestra download + processamento."""
    auth = _resolver_webdav_auth()
    pasta_mes = resolver_pasta_mes_atual(auth)
    print(f"[cnpj_ingest] Usando dados do mês: {pasta_mes}")

    zips_dir = config.DATA_RAW_DIR / "zips"
    zips_dir.mkdir(exist_ok=True)

    municipios_alvo = resolver_municipios_alvo(pasta_mes, auth, zips_dir)
    print(f"[cnpj_ingest] Códigos de município da Grande Vitória resolvidos: {municipios_alvo}")

    empresas_urls = _listar_arquivos(pasta_mes, "Empresas", auth)
    estabelecimentos_urls = _listar_arquivos(pasta_mes, "Estabelecimentos", auth)
    simples_urls = _listar_arquivos(pasta_mes, "Simples", auth)

    empresas_paths, estab_paths = [], []
    for caminho in empresas_urls:
        destino = zips_dir / Path(caminho).name
        baixar_arquivo(caminho, destino, auth)
        empresas_paths.append(destino)
    for caminho in estabelecimentos_urls:
        destino = zips_dir / Path(caminho).name
        baixar_arquivo(caminho, destino, auth)
        estab_paths.append(destino)

    simples_path = None
    if simples_urls:
        simples_path = zips_dir / Path(simples_urls[0]).name
        baixar_arquivo(simples_urls[0], simples_path, auth)

    processar_estabelecimentos_e_empresas(empresas_paths, estab_paths, simples_path, municipios_alvo)


if __name__ == "__main__":
    executar()
