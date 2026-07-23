"""
Servidor MCP do dataset de empresas da Grande Vitória.

Expõe o dataset consolidado como ferramentas MCP, para o Claude (ou qualquer
cliente MCP) consultar diretamente — buscar empresas por filtros de
prospecção, obter a visão 360º de um CNPJ e ver estatísticas do dataset.

Rodar (transporte stdio, padrão para clientes MCP como o Claude Desktop /
Claude Code):
    python mcp_server.py

Configuração no cliente MCP (ex.: claude_desktop_config.json ou .mcp.json):
    {
      "mcpServers": {
        "grande-vitoria-empresas": {
          "command": "/CAMINHO/para/.venv/bin/python",
          "args": ["/CAMINHO/para/mcp_server.py"]
        }
      }
    }
"""
from mcp.server.fastmcp import FastMCP

from src import dataset_queries

mcp = FastMCP("grande-vitoria-empresas")


@mcp.tool()
def estatisticas() -> dict:
    """Panorama geral do dataset: total de empresas, distribuição por
    município/porte/regime tributário, top CNAEs, quantas têm telefone/e-mail
    e contagem de registros de cada fonte (processos, sanções, etc.)."""
    return dataset_queries.estatisticas()


@mcp.tool()
def buscar_empresas(
    municipio: str = None,
    cnae: str = None,
    cnae_prefix: str = None,
    porte: str = None,
    regime_tributario: str = None,
    texto: str = None,
    tem_pendencia: bool = None,
    com_telefone: bool = None,
    com_email: bool = None,
    com_whatsapp: bool = None,
    com_rede_social: bool = None,
    com_processos: bool = None,
    com_sancoes: bool = None,
    com_ambiental: bool = None,
    com_divida: bool = None,
    capital_min: float = None,
    capital_max: float = None,
    ordenar_por: str = "razao_social",
    limite: int = 50,
    offset: int = 0,
) -> dict:
    """Busca empresas com filtros combináveis (todos opcionais), para
    prospecção de clientes.

    - municipio: nome da cidade (Vitória, Vila Velha, Serra, Cariacica,
      Viana, Guarapari, Fundão) — aceita com ou sem acento.
    - cnae: código CNAE (bate no principal ou nos secundários).
    - porte / regime_tributario: filtros exatos (ex.: regime "MEI",
      "Simples Nacional", "Normal").
    - texto: busca por parte da razão social ou nome fantasia.
    - tem_pendencia: True = só com pendência jurídico-fiscal; False = só
      "limpas" (bom filtro de prospecção); None = ignora.
    - com_telefone / com_email: True exige o contato preenchido.
    - com_whatsapp: True exige link de WhatsApp (requer a etapa `contato`).
    - com_rede_social: True exige Instagram/Facebook/LinkedIn (etapa `contato`).
    - capital_min / capital_max: faixa de capital social (R$).
    - ordenar_por: razao_social | capital_social | municipio | porte | cnpj.
    - limite (máx. 500) e offset para paginação.

    Retorna {'total', 'limite', 'offset', 'itens': [...]}.
    """
    return dataset_queries.buscar_empresas(
        municipio=municipio, cnae=cnae, cnae_prefix=cnae_prefix, porte=porte,
        regime_tributario=regime_tributario, texto=texto,
        tem_pendencia=tem_pendencia, com_telefone=com_telefone,
        com_email=com_email, com_whatsapp=com_whatsapp,
        com_rede_social=com_rede_social, com_processos=com_processos,
        com_sancoes=com_sancoes, com_ambiental=com_ambiental, com_divida=com_divida,
        capital_min=capital_min, capital_max=capital_max, ordenar_por=ordenar_por,
        limite=limite, offset=offset,
    )


@mcp.tool()
def obter_empresa(cnpj: str) -> dict:
    """Visão 360º de uma empresa pelo CNPJ (14 dígitos): dados cadastrais,
    sócios, complemento JUCEES, geolocalização e todas as pendências
    (processos, sanções, infrações ambientais, dívida ativa) com um resumo
    agregado. Retorna null se o CNPJ não estiver na base."""
    resultado = dataset_queries.obter_empresa(cnpj)
    if resultado is None:
        return {"erro": f"CNPJ {cnpj} não encontrado na base."}
    return resultado


@mcp.tool()
def classificar_empresas(
    objetivo: str = "generico",
    pref_telefone: bool = None,
    pref_email: bool = None,
    pref_whatsapp: bool = None,
    pref_rede: bool = None,
    portes: list = None,
    presenca: str = "indiferente",
    fiscal: str = "indiferente",
    municipio: str = None,
    cnae_prefix: str = None,
    texto: str = None,
    capital_min: float = None,
    capital_max: float = None,
    limite: int = 50,
) -> dict:
    """Classifica/pontua empresas para prospecção conforme um objetivo, e as
    devolve ranqueadas por um score 0-100 com rótulo (Quente/Morno/Frio).

    - objetivo: define o que conta como bom lead —
      "regularizacao" (contábil/jurídico: prioriza quem tem dívida ativa),
      "marketing" (prioriza quem NÃO tem site/redes = oportunidade digital),
      "credito" (prioriza empresas sem pendências), "software" (porte +
      presença digital), "generico" (equilibrado).
    - pref_telefone/pref_email/pref_whatsapp/pref_rede: dão pontos a quem tem
      esse canal de contato.
    - portes: lista de códigos de porte alvo (pontua quem está na lista).
    - presenca: "com" | "sem" | "indiferente" (presença digital: site/redes).
    - fiscal: "limpas" | "com_pendencia" | "indiferente".
    - municipio/cnae_prefix/texto/capital_min/capital_max: recortam a base
      antes de pontuar. limite (máx. 500).

    Retorna {'total','pontos_maximos','itens': [... com score, score_pct,
    classificacao]}.
    """
    return dataset_queries.classificar_empresas(
        objetivo=objetivo, pref_telefone=pref_telefone, pref_email=pref_email,
        pref_whatsapp=pref_whatsapp, pref_rede=pref_rede, portes=portes,
        presenca=presenca, fiscal=fiscal, municipio=municipio,
        cnae_prefix=cnae_prefix, texto=texto, capital_min=capital_min,
        capital_max=capital_max, limite=limite,
    )


if __name__ == "__main__":
    mcp.run()
