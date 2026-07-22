"""
Configuração central do pipeline de dados de empresas da Grande Vitória.

Toda credencial sensível (API keys) é lida de variáveis de ambiente,
nunca hardcoded aqui.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
CHECKPOINT_DIR = BASE_DIR / "data" / "checkpoints"
DB_PATH = BASE_DIR / "data" / "grande_vitoria.db"

for d in (DATA_RAW_DIR, CHECKPOINT_DIR, DB_PATH.parent):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Escopo geográfico — Grande Vitória
# A base da Receita Federal identifica município por NOME (coluna 'uf' +
# nome em Municipios.csv), não pelo código IBGE de 7 dígitos. Por isso
# filtramos por UF='ES' + nome do município em maiúsculo sem acento.
# ---------------------------------------------------------------------------
UF_ALVO = "ES"
MUNICIPIOS_GRANDE_VITORIA = {
    "VITORIA",
    "VILA VELHA",
    "SERRA",
    "CARIACICA",
    "VIANA",
    "GUARAPARI",
    "FUNDAO",  # opcional: alguns estudos incluem Fundão na RMGV
}

# Códigos IBGE (7 dígitos) — usados apenas para bases que já usam padrão IBGE
# (ex.: RAIS/CAGED, IBGE CEMPRE), não para o arquivo bruto da Receita.
MUNICIPIOS_IBGE = {
    "VITORIA": "3205200",
    "VILA VELHA": "3205309",
    "SERRA": "3205002",
    "CARIACICA": "3201308",
    "VIANA": "3205010",
    "GUARAPARI": "3202405",
    "FUNDAO": "3202405",  # ajustar se for usar — conferir código exato
}

# ---------------------------------------------------------------------------
# Fontes — Receita Federal (CNPJ)
# A RF migrou a hospedagem dos dados abertos para uma instância Nextcloud
# (confirmado em 21/07/2026): a antiga URL de índice HTML
# (arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/) agora
# devolve 404 e o domínio raiz redireciona para um link de compartilhamento
# público (/index.php/s/<token>). O token do link pode mudar se a RF
# recriar o compartilhamento, por isso cnpj_ingest.py o resolve
# dinamicamente a cada execução (segue o redirect de RFB_ROOT_URL) em vez
# de fixá-lo aqui. A listagem de pastas/arquivos é feita via WebDAV
# público do Nextcloud (PROPFIND), não mais parsing de HTML.
# ---------------------------------------------------------------------------
RFB_ROOT_URL = "https://arquivos.receitafederal.gov.br/"
RFB_WEBDAV_BASE_URL = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
RFB_CNPJ_WEBDAV_PATH = "Dados/Cadastros/CNPJ"

# ---------------------------------------------------------------------------
# JUCEES (Junta Comercial do ES) — via portal de dados abertos do Governo
# do ES (dados.es.gov.br, CKAN). URL estável baseada no resource_id do
# CKAN — não muda mensalmente como outras fontes (confirmado: o link segue
# o padrão /datastore/dump/<resource_id>, independente do nome do arquivo).
#
# LIMITAÇÃO IMPORTANTE: este dataset específico só cobre empresas com
# natureza jurídica 'Sociedade Empresária' do ramo de serviços e comércio
# — não é o universo completo de empresas do ES (não inclui MEI, Empresário
# Individual, etc.). É um complemento à base da Receita Federal (que já
# cobre tudo), não um substituto. Traz de diferencial: NIRE, data de
# constituição e natureza jurídica descritiva.
#
# Referência: https://dados.es.gov.br/dataset/empresas
# ---------------------------------------------------------------------------
JUCEES_RESOURCE_ID = "f3f7fed7-9d67-4616-962e-d3084146eab9"
JUCEES_DATASTORE_DUMP_URL = os.environ.get(
    "JUCEES_DUMP_URL",
    f"https://dados.es.gov.br/datastore/dump/{JUCEES_RESOURCE_ID}?bom=True",
)

# ---------------------------------------------------------------------------
# TCEES (Tribunal de Contas do ES) — listas de responsáveis/sanções
# estaduais, via portal de dados abertos do ES (mesma plataforma CKAN da
# JUCEES). URLs estáveis por resource_id. Todas trazem o documento
# (CPF/CNPJ) da parte, permitindo cruzamento direto por CNPJ.
#
# Estas listas complementam o CEIS/CNEP FEDERAL (Portal da Transparência):
# são sanções aplicadas pelo Tribunal de Contas ESTADUAL, que não aparecem
# na base federal. Layout confirmado (dicionário oficial):
#   NomeResponsavel, TipoDocumentoResponsavel, NumeroDocumentoResponsavel,
#   NumeroProcesso, AnoProcesso, TipoDeliberacao, NumeroDeliberacao,
#   AnoDeliberacao, DataTransito, DataTermino, Jurisdicionado
#
# Referência: https://www.tcees.tc.br/portal-da-transparencia/dados-abertos/
# ---------------------------------------------------------------------------
TCEES_LISTAS = {
    "TCEES - Empresa Inidônea": "ca979cb0-7ee5-4d91-af6c-804a353b9ef2",
    "TCEES - Proibido de Contratar": "2c27a170-e415-4b9d-9679-49a65903979a",
    "TCEES - Inabilitado": "4fe9a28d-02b4-438b-851b-ea33904f2344",
    "TCEES - Contas Irregulares": "d2a18709-9c15-46da-bdbd-fbc3ddbc2202",
}
TCEES_DUMP_URL_TEMPLATE = "https://dados.es.gov.br/datastore/dump/{resource_id}?bom=True"

# ---------------------------------------------------------------------------
# Fontes — Portal da Transparência, IBAMA (URLs de arquivo, coladas à mão)
#
# Essas páginas geram o link de exportação via navegação/JS, então não dá
# pra apontar direto para a página do dataset. Duas opções:
#   A) Cole a URL final do arquivo (.csv/.zip) — abra a página, clique no
#      botão de exportação/download e copie a URL do arquivo gerado.
#   B) Mais simples: baixe o arquivo pelo navegador (Ctrl+S no botão de
#      export) e cole aqui o CAMINHO LOCAL do arquivo salvo, ex.:
#      CEIS_FILE_URL=/home/usuario/Downloads/ceis_202606.csv
#      O pipeline aceita as duas formas — se não começar com "http", trata
#      como caminho de arquivo local.
#
# Páginas de referência para localizar o botão de exportação:
#   CEIS  -> https://portaldatransparencia.gov.br/download-de-dados/ceis
#   CNEP  -> https://portaldatransparencia.gov.br/download-de-dados/cnep
#   CEPIM -> https://portaldatransparencia.gov.br/download-de-dados/cepim
#   PGFN Dívida Ativa -> https://dados.gov.br/dados/conjuntos-dados/divida-ativa-da-uniao
#   IBAMA Autos de Infração -> https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-auto-de-infracao
# ---------------------------------------------------------------------------
CEIS_URL = os.environ.get("CEIS_FILE_URL", "COLE_AQUI_A_URL_DO_ARQUIVO_CEIS")
CNEP_URL = os.environ.get("CNEP_FILE_URL", "COLE_AQUI_A_URL_DO_ARQUIVO_CNEP")
CEPIM_URL = os.environ.get("CEPIM_FILE_URL", "COLE_AQUI_A_URL_DO_ARQUIVO_CEPIM")
PGFN_DIVIDA_ATIVA_URL = os.environ.get("PGFN_FILE_URL", "COLE_AQUI_A_URL_DO_ARQUIVO_DIVIDA_ATIVA")
IBAMA_AUTOS_INFRACAO_URL = os.environ.get("IBAMA_FILE_URL", "COLE_AQUI_A_URL_DO_ARQUIVO_IBAMA")

# Extensões aceitas como "arquivo de verdade" — usado pela validação em
# src/url_validation.py para pegar erro de URL errada ANTES de gastar
# tempo baixando um HTML de página por engano.
EXTENSOES_ARQUIVO_VALIDAS = (".csv", ".zip", ".xlsx", ".json")

# ---------------------------------------------------------------------------
# DataJud (CNJ) — API pública de processos judiciais
# Requer chave pública documentada pelo CNJ (gratuita, mas com rate limit).
# https://datajud-wiki.cnj.jus.br/api-publica/
# ---------------------------------------------------------------------------
# A autenticação é feita com uma CHAVE PÚBLICA ÚNICA, gerada e mantida
# pelo DPJ/CNJ — não é uma chave pessoal, é a mesma para todo mundo.
# A vigente (capturada em 21/07/2026) está fixada abaixo como fallback,
# mas o CNJ pode trocá-la a qualquer momento por motivo de segurança.
# Se a API começar a retornar 401/403, é sinal de que ela mudou — pegue a
# atualizada em https://datajud-wiki.cnj.jus.br/api-publica/acesso/ e
# sobrescreva via variável de ambiente DATAJUD_API_KEY (não precisa editar
# este arquivo).
DATAJUD_API_KEY_FALLBACK = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
# "or" (não o 2º argumento de os.environ.get) é proposital: quando o .env é
# carregado via `source` com a linha "DATAJUD_API_KEY=" (vazia), a variável
# passa a EXISTIR no ambiente com valor "" — os.environ.get(chave, default)
# só usaria o default se a chave estivesse ausente, então retornaria "" em
# vez do fallback. Com "or", string vazia também cai no fallback.
DATAJUD_API_KEY = os.environ.get("DATAJUD_API_KEY") or DATAJUD_API_KEY_FALLBACK
DATAJUD_WIKI_URL = "https://datajud-wiki.cnj.jus.br/api-publica/acesso/"
DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"
# Tribunais relevantes para empresas sediadas no ES (adicionar TRTs/TRFs
# conforme o tipo de processo que se busca — trabalhista, federal, etc.)
DATAJUD_TRIBUNAIS = {
    "tjes": "api_publica_tjes",   # Justiça Estadual ES
    "trt17": "api_publica_trt17",  # Justiça do Trabalho ES
    "trf2": "api_publica_trf2",   # Justiça Federal (ES pertence à 2ª Região)
}
DATAJUD_RATE_LIMIT_SLEEP_SECONDS = 1.2  # ajustar conforme limite documentado

# ---------------------------------------------------------------------------
# OpenStreetMap Nominatim — enriquecimento geográfico (geocodificação),
# gratuito e sem cartão de crédito. Trade-off: só traz lat/long, não traz
# telefone/site/avaliação/horário (isso só o Google Places tem, mas exige
# cartão cadastrado no Google Cloud).
# Política de uso obrigatória: https://operations.osmfoundation.org/policies/nominatim/
# ---------------------------------------------------------------------------
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
NOMINATIM_USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "grande-vitoria-empresas-dataset/1.0 (uso interno, sem contato configurado)",
)
NOMINATIM_RATE_LIMIT_SLEEP_SECONDS = 1.1  # política exige no máx. 1 req/s

# ---------------------------------------------------------------------------
# Enriquecimento de contato / redes sociais (etapa `contato`) — 100% grátis:
#   - WhatsApp: derivado do telefone (link wa.me, não verificado)
#   - Site: inferido do domínio do e-mail corporativo
#   - Redes sociais: extraídas do HTML do site da PRÓPRIA empresa (legítimo;
#     não raspa Instagram/Facebook/LinkedIn direto, o que violaria os ToS)
# ---------------------------------------------------------------------------
CONTATO_HTTP_TIMEOUT = 10           # timeout por site (segundos)
CONTATO_RATE_LIMIT_SLEEP_SECONDS = 0.3  # pausa educada entre fetches de site
CONTATO_USER_AGENT = NOMINATIM_USER_AGENT  # reaproveita o UA identificado
# Provedores de e-mail genéricos — NÃO servem para inferir o site da empresa.
EMAIL_DOMINIOS_GENERICOS = {
    "gmail.com", "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br",
    "yahoo.com", "yahoo.com.br", "bol.com.br", "uol.com.br", "terra.com.br",
    "ig.com.br", "live.com", "icloud.com", "globo.com", "globomail.com",
    "r7.com", "msn.com", "aol.com", "zipmail.com.br", "me.com", "gmx.com",
    "protonmail.com", "yahoo.com.mx", "hotmail.es",
}

# ---------------------------------------------------------------------------
# Matching fuzzy (para sanções/processos sem CNPJ explícito)
# ---------------------------------------------------------------------------
FUZZY_MATCH_THRESHOLD = 90  # 0-100, usado com rapidfuzz.fuzz.token_sort_ratio
