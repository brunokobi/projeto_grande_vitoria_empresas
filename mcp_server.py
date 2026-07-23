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
        com_rede_social=com_rede_social, capital_min=capital_min,
        capital_max=capital_max, ordenar_por=ordenar_por,
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


if __name__ == "__main__":
    mcp.run()
