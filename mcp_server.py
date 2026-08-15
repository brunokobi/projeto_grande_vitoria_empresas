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

from src import dataset_queries, geocode

mcp = FastMCP("grande-vitoria-empresas")


@mcp.tool()
def estatisticas() -> dict:
    """Panorama geral do dataset: total de empresas, distribuição por
    município/porte/regime tributário, top CNAEs, quantas têm telefone/e-mail
    e contagem de registros de cada fonte (processos, sanções, etc.)."""
    return dataset_queries.estatisticas()


@mcp.tool()
def classes_processos(limite: int = 100) -> list:
    """Classes de processo judicial mais frequentes na base (com contagem
    de registros) — use pra saber quais valores passar em
    buscar_empresas(processo_classe=...). Ex.: "AçãO TRABALHISTA - RITO
    ORDINáRIO", "PROCEDIMENTO COMUM CíVEL", "EXECUçãO FISCAL"."""
    return dataset_queries.classes_processos(limite=limite)


@mcp.tool()
def ranking_doacoes_eleitorais(limite: int = 20) -> dict:
    """Ranking de doações eleitorais (TSE) — responde direto perguntas como
    "quais candidatos mais receberam doação" ou "quais empresas mais
    doaram", sem precisar varrer empresa por empresa. Devolve 4 listas já
    ordenadas: candidatos_por_quantidade, candidatos_por_valor,
    empresas_por_quantidade, empresas_por_valor (cada item com nº de
    doações e valor total em R$; nas empresas, também os sócios envolvidos).

    Atenção: o vínculo é por SÓCIO — se a mesma pessoa é sócia de várias
    empresas, a doação aparece em todas elas (não são doações distintas)."""
    return dataset_queries.ranking_doacoes_eleitorais(limite=limite)


@mcp.tool()
def buscar_empresas(
    municipio: str = None,
    cnae: str = None,
    cnae_prefix: str = None,
    porte: str = None,
    regime_tributario: str = None,
    texto: str = None,
    socio: str = None,
    tem_pendencia: bool = None,
    com_telefone: bool = None,
    com_email: bool = None,
    com_whatsapp: bool = None,
    com_rede_social: bool = None,
    com_processos: bool = None,
    processo_polo: str = None,
    processo_classe: str = None,
    com_sancoes: bool = None,
    com_ambiental: bool = None,
    com_divida: bool = None,
    com_trabalho_escravo: bool = None,
    com_cepim: bool = None,
    com_leniencia: bool = None,
    com_contratos_governamentais: bool = None,
    com_renuncia_fiscal: bool = None,
    com_imune_isento: bool = None,
    com_habilitado_beneficio: bool = None,
    com_vinculo_politico: bool = None,
    com_contrato_pncp: bool = None,
    com_marca_registrada: bool = None,
    com_incentivo_estadual: bool = None,
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
    - com_processos: True exige processo judicial. Por padrão só conta
      quando a empresa é RÉ (é o que representa risco/pendência) — passe
      processo_polo="Autor"/"Terceiro"/"TODOS" pra mudar isso.
    - processo_classe: restringe à classe exata do processo (ex.: "AçãO
      TRABALHISTA - RITO ORDINáRIO", "PROCEDIMENTO COMUM CíVEL" — ver
      ferramenta classes_processos pra lista completa).
    - com_telefone / com_email: True exige o contato preenchido.
    - com_whatsapp: True exige link de WhatsApp (requer a etapa `contato`).
    - com_rede_social: True exige Instagram/Facebook/LinkedIn (etapa `contato`).
    - capital_min / capital_max: faixa de capital social (R$).
    - com_contratos_governamentais: True exige contrato com órgão público
      federal (Portal da Transparência).
    - com_renuncia_fiscal: True exige renúncia fiscal federal registrada
      (valor R$ em algum ano).
    - com_imune_isento: True exige imunidade/isenção de IRPJ (comum em
      igrejas, sindicatos, associações).
    - com_habilitado_beneficio: True exige habilitação a regime de
      benefício fiscal específico (ex.: RET - Incorporação Imobiliária).
    - com_vinculo_politico: True exige vínculo político do sócio (PEP,
      candidatura no TSE, ou doação eleitoral pessoal).
    - com_contrato_pncp: True exige contrato via PNCP (Portal Nacional de
      Contratações Públicas — municipal/estadual/federal, cobertura bem
      mais ampla que com_contratos_governamentais, que é só federal).
    - com_marca_registrada: True exige marca registrada no INPI.
    - com_incentivo_estadual: True exige incentivo fiscal de ICMS estadual
      (Programa COMPETE-ES).
    - ordenar_por: razao_social | capital_social | municipio | porte | cnpj.
    - limite (máx. 500) e offset para paginação.

    Retorna {'total', 'limite', 'offset', 'itens': [...]}.
    """
    return dataset_queries.buscar_empresas(
        municipio=municipio, cnae=cnae, cnae_prefix=cnae_prefix, porte=porte,
        regime_tributario=regime_tributario, texto=texto, socio=socio,
        tem_pendencia=tem_pendencia, com_telefone=com_telefone,
        com_email=com_email, com_whatsapp=com_whatsapp,
        com_rede_social=com_rede_social, com_processos=com_processos,
        processo_polo=processo_polo, processo_classe=processo_classe,
        com_sancoes=com_sancoes, com_ambiental=com_ambiental, com_divida=com_divida,
        com_trabalho_escravo=com_trabalho_escravo, com_cepim=com_cepim,
        com_leniencia=com_leniencia,
        com_contratos_governamentais=com_contratos_governamentais,
        com_renuncia_fiscal=com_renuncia_fiscal, com_imune_isento=com_imune_isento,
        com_habilitado_beneficio=com_habilitado_beneficio,
        com_vinculo_politico=com_vinculo_politico,
        com_contrato_pncp=com_contrato_pncp, com_marca_registrada=com_marca_registrada,
        com_incentivo_estadual=com_incentivo_estadual,
        capital_min=capital_min, capital_max=capital_max, ordenar_por=ordenar_por,
        limite=limite, offset=offset,
    )


@mcp.tool()
def buscar_empresas_perto(
    endereco: str = None,
    lat: float = None,
    lon: float = None,
    raio_km: float = 5,
    municipio: str = None,
    cnae_prefix: str = None,
    porte: str = None,
    tem_pendencia: bool = None,
    com_telefone: bool = None,
    com_email: bool = None,
    limite: int = 50,
) -> dict:
    """Busca empresas geocodificadas dentro de um raio (em km) de um ponto,
    ordenadas da mais próxima pra mais longe.

    Informe OU `endereco` (um texto livre — é geocodificado automaticamente
    via Nominatim/OSM) OU `lat`+`lon` diretos — não precisa dos dois. Pra
    buscar perto de OUTRA EMPRESA, chame obter_empresa nela primeiro pra
    pegar a geolocalização dela e use lat/lon daqui.

    Combina com os mesmos filtros de município/CNAE/porte/pendência/contato
    de buscar_empresas. Retorna {'total','centro','raio_km','itens': [...
    com distancia_km, em km]}, ou {'erro': ...} se o endereço não for
    encontrado ou nem endereço nem lat/lon forem informados.
    """
    if lat is None or lon is None:
        if not endereco:
            return {"erro": "Informe 'endereco' ou 'lat'+'lon'."}
        ponto = geocode.resolver_endereco(endereco)
        if ponto["lat"] is None:
            return {"erro": f"Não consegui geocodificar '{endereco}'."}
        lat, lon = ponto["lat"], ponto["lon"]
    return dataset_queries.buscar_por_raio(
        lat=lat, lon=lon, raio_km=raio_km, municipio=municipio,
        cnae_prefix=cnae_prefix, porte=porte, tem_pendencia=tem_pendencia,
        com_telefone=com_telefone, com_email=com_email, limite=limite,
    )


@mcp.tool()
def obter_empresa(cnpj: str) -> dict:
    """Visão 360º de uma empresa pelo CNPJ (14 dígitos): dados cadastrais,
    sócios, complemento JUCEES, geolocalização, todas as pendências
    (processos, sanções, infrações ambientais, dívida ativa), vínculos
    políticos de sócios (PEP, candidaturas e doações no TSE), contratos com
    órgãos públicos (federais via Portal da Transparência e municipais/
    estaduais/federais via PNCP), benefícios/renúncias fiscais (renúncia
    fiscal por ano, imunidade/isenção de IRPJ, habilitação a regime de
    benefício) e marcas registradas no INPI, com um resumo agregado.
    Retorna null se o CNPJ não estiver na base."""
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
