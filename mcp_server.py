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
from mcp.server.fastmcp import Context, FastMCP

from src import contas, dataset_queries, geocode

mcp = FastMCP("grande-vitoria-empresas")


@mcp.tool()
def estatisticas() -> dict:
    """Panorama geral do dataset: total de empresas, distribuição por
    município/porte/regime tributário, top CNAEs, quantas têm telefone/e-mail
    e contagem de registros de cada fonte (processos, sanções, etc.), mais
    `empresas_por_flag` (quantas empresas em cada filtro, inclusive os novos:
    devedor_contumaz_es, insolvencia, par_es, contrato_tcees,
    contrato_estadual_es, incentivo_invest_es, socio_estrangeiro, grupo_economico)
    e a distribuição da nota de integridade."""
    return dataset_queries.estatisticas()


@mcp.tool()
def classes_processos(limite: int = 100) -> list:
    """Classes de processo judicial mais frequentes na base (com contagem
    de registros) — use pra saber quais valores passar em
    buscar_empresas(processo_classe=...). Ex.: "AçãO TRABALHISTA - RITO
    ORDINáRIO", "PROCEDIMENTO COMUM CíVEL", "EXECUçãO FISCAL"."""
    return dataset_queries.classes_processos(limite=limite)


@mcp.tool()
def orgaos_sancionadores(limite: int = 100) -> list:
    """Órgãos sancionadores mais frequentes na base (com contagem de
    registros) — use pra saber quais valores passar em
    buscar_empresas(sancao_orgao=...)."""
    return dataset_queries.orgaos_sancionadores(limite=limite)


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
    com_site: bool = None,
    com_processos: bool = None,
    processo_polo: list = None,
    processo_classe: list = None,
    com_sancoes: bool = None,
    sancao_tipo: list = None,
    sancao_orgao: str = None,
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
    vinculo_fonte: list = None,
    com_contrato_pncp: bool = None,
    pncp_categoria: list = None,
    com_marca_registrada: bool = None,
    com_incentivo_estadual: bool = None,
    com_devedor_contumaz: bool = None,
    com_insolvencia: bool = None,
    com_par_es: bool = None,
    com_contrato_tcees: bool = None,
    com_contrato_estadual_es: bool = None,
    com_beneficio_fiscal: bool = None,
    beneficio_tipo: list = None,
    com_unidade_conservacao: bool = None,
    com_ambiental_proximidade: bool = None,
    ambiental_proximidade_tipo: list = None,
    com_risco_geologico: bool = None,
    risco_geologico_grau: list = None,
    cnpj: str = None,
    nivel_integridade: list = None,
    com_ocorrencia_socio: bool = None,
    ocorrencia_fonte: list = None,
    ocorrencia_criterio_forte: bool = None,
    com_socio_estrangeiro: bool = None,
    socio_estrangeiro_gafi: bool = None,
    com_grupo_economico: bool = None,
    grupo_relacao: list = None,
    grupo_min_empresas: int = None,
    processo_validacao: list = None,
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
      processo_polo="Autor"/"Terceiro"/"TODOS" pra mudar isso. Passar uma
      LISTA (ex.: ["Réu","Autor"]) é AND, não OR: exige processo de CADA
      polo da lista (empresa que é ré em algum processo E autora em outro),
      não só de algum deles.
    - processo_classe: restringe à classe exata do processo (ex.: "AçãO
      TRABALHISTA - RITO ORDINáRIO", "PROCEDIMENTO COMUM CíVEL" — ver
      ferramenta classes_processos pra lista completa). Uma lista aqui
      também é AND: exige processo de CADA classe listada.
    - com_sancoes: True exige sanção administrativa (CEIS/CNEP/CEPIM/
      trabalho escravo/TCEES). sancao_tipo restringe o(s) tipo(s)
      específico(s) (string única ou lista — lista é AND, exige sanção de
      CADA tipo listado, "TODOS" pra qualquer); sancao_orgao restringe ao
      órgão sancionador exato (ver ferramenta orgaos_sancionadores pra
      lista completa).
    - com_telefone / com_email: True exige o contato preenchido.
    - com_whatsapp: True exige WhatsApp publicado pela própria empresa no
      site confirmado (link wa.me / api.whatsapp.com). Dado provável.
    - com_site: True exige site confirmado como da empresa (Registro.br, CNPJ
      no site ou e-mail da Receita compatível). Dado provável; a coleta começa
      pelas maiores empresas e ainda não cobre a base toda.
    - com_rede_social: True exige rede social (Instagram, Facebook, LinkedIn,
      YouTube, X ou TikTok) publicada nesse site confirmado.
    - capital_min / capital_max: faixa de capital social (R$).
    - cnpj: CNPJ (14 dígitos ou só a raiz de 8) — atalho pra achar a empresa.
    - nivel_integridade: nível da nota de risco de integridade —
      "Baixo"/"Moderado"/"Alto"/"Crítico" (lista = OU). Pré-calculado com a
      mesma função do modal; metodologia na página de fontes do site.
    - com_ocorrencia_socio: True exige sócio com ocorrência em fonte pública
      (due diligence: cruzamento por CPF mascarado + nome ou só nome, sempre
      "possível correspondência"). ocorrencia_fonte restringe a fonte(s):
      PGFN_PF, SERVIDOR_FEDERAL, CEAF, BOLSA_FAMILIA, IBAMA_EMBARGO,
      BCB_INABILITADO, CVM_SANCIONADOR, TCU_INABILITADO, OFAC, ONU,
      UK_SANCOES, ICIJ_OFFSHORE (lista = OU). ocorrencia_criterio_forte=True
      exige o critério mais forte (CPF mascarado + nome).
    - com_socio_estrangeiro: True exige sócio residente no exterior;
      socio_estrangeiro_gafi=True só país da lista do GAFI (país com código
      ambíguo na Receita fica de fora).
    - com_grupo_economico: True exige ligação societária com outras empresas
      (base nacional da Receita). grupo_relacao: "socio_em_comum",
      "empresa_socia", "participacao" (lista = OU); grupo_min_empresas: nº
      mínimo de OUTRAS empresas ligadas.
    - processo_validacao: com com_processos, só processos cujo vínculo com a
      empresa foi conferido: "cnpj_confirmado", "nome_unico_brasil",
      "nome_repetido", "homonimo_mesmo_estado" (lista = OU).
    - com_contratos_governamentais: True exige contrato com órgão público
      federal (Portal da Transparência).
    - com_renuncia_fiscal: True exige renúncia fiscal federal registrada
      (valor R$ em algum ano).
    - com_imune_isento: True exige imunidade/isenção de IRPJ (comum em
      igrejas, sindicatos, associações).
    - com_habilitado_beneficio: True exige habilitação a regime de
      benefício fiscal específico (ex.: RET - Incorporação Imobiliária).
    - com_vinculo_politico: True exige vínculo político do sócio (PEP,
      candidatura no TSE, ou doação eleitoral pessoal). vinculo_fonte
      restringe a fonte (TSE_DOACAO/TSE_CANDIDATURA, "TODOS" pra qualquer)
      — passar os DOIS numa lista é AND: só empresas cujo sócio TENHA os
      dois (é candidato E doou), não qualquer um dos dois.
    - com_contrato_pncp: True exige contrato via PNCP (Portal Nacional de
      Contratações Públicas — municipal/estadual/federal, cobertura bem
      mais ampla que com_contratos_governamentais, que é só federal).
      pncp_categoria restringe à(s) categoria(s) exata(s) (ex.: "Compras",
      "Serviços", "Obras") — uma lista é AND, exige contrato de CADA
      categoria listada.
    - com_marca_registrada: True exige marca registrada no INPI.
    - com_incentivo_estadual: True exige incentivo fiscal de ICMS estadual
      (Programa COMPETE-ES).
    - com_par_es: True exige Processo Administrativo de Responsabilização
      (Lei Anticorrupção) no Governo do ES (SECONT).
    - com_contrato_tcees: True exige contrato com prefeitura, câmara ou órgão
      estadual capixaba (TCEES, desde 2021).
    - com_contrato_estadual_es: True exige contrato do Governo do ES (SEGER).
    - com_insolvencia: True exige empresa em recuperação judicial ou falência
      segundo a Receita (EM RECUPERACAO JUDICIAL / MASSA FALIDA na razão social).
    - com_devedor_contumaz: True exige o grupo (raiz do CNPJ) na lista oficial
      de devedores contumazes de ICMS da SEFAZ-ES (Lei 12.124/2024).
    - com_beneficio_fiscal: True exige qualquer benefício fiscal (renúncia,
      imune/isento, habilitado ou incentivo ICMS — engloba os 4 filtros
      acima num só). beneficio_tipo restringe o(s) tipo(s) específico(s)
      (RENUNCIA/IMUNE_ISENTO/HABILITADO/COMPETE_ES/INVEST_ES) — uma lista é AND,
      exige benefício de CADA tipo listado.
    - com_unidade_conservacao: True exige que a empresa esteja geolocalizada
      DENTRO de alguma Unidade de Conservação ou Zona de Amortecimento
      (MMA/CNUC + IEMA-ES) — sinal de contexto ambiental, não é sanção.
    - com_ambiental_proximidade: True exige que a empresa esteja a até 500m
      de um ponto de fiscalização ambiental grave, barragem ou outorga
      hídrica. IMPORTANTE: essas 3 fontes públicas não trazem CNPJ/nome de
      quem foi autuado ou outorgado, só localização — é sinal de
      PROXIMIDADE ("tem uma ocorrência ambiental relevante por perto"), não
      de identidade ("essa empresa foi autuada/outorgada"). Exceção parcial:
      barragem tem o campo interessado (nome), então parte dos vínculos de
      tipo="barragem" tem match_confianca="socio" (nome bate com sócio da
      empresa, é identidade de verdade) em vez de "proximidade".
      ambiental_proximidade_tipo restringe o(s) tipo(s)
      (fiscalizacao/barragem/outorga) — uma lista é AND.
    - com_risco_geologico: True exige que a empresa esteja geolocalizada
      DENTRO de algum setor de risco geológico/inundação mapeado (Defesa
      Civil/CPRM/PMRR Serra-Viana) — sinal de contexto (exposição física a
      deslizamento/enchente), não é sanção. Cobertura é desigual entre os 7
      municípios (reflete onde há setor mapeado, não a ausência real de
      risco onde não há polígono). risco_geologico_grau restringe o grau
      (Baixo/Médio/Alto/Muito Alto) — uma lista é AND.
    - ordenar_por: razao_social | capital_social | municipio | porte | cnpj.
    - limite (máx. 500) e offset para paginação.

    Retorna {'total', 'limite', 'offset', 'itens': [...]}.
    """
    return dataset_queries.buscar_empresas(
        municipio=municipio, cnae=cnae, cnae_prefix=cnae_prefix, porte=porte,
        regime_tributario=regime_tributario, texto=texto, socio=socio,
        tem_pendencia=tem_pendencia, com_telefone=com_telefone,
        com_email=com_email, com_whatsapp=com_whatsapp,
        com_rede_social=com_rede_social, com_site=com_site, com_processos=com_processos,
        processo_polo=processo_polo, processo_classe=processo_classe,
        com_sancoes=com_sancoes, sancao_tipo=sancao_tipo, sancao_orgao=sancao_orgao,
        com_ambiental=com_ambiental, com_divida=com_divida,
        com_trabalho_escravo=com_trabalho_escravo, com_cepim=com_cepim,
        com_leniencia=com_leniencia,
        com_contratos_governamentais=com_contratos_governamentais,
        com_renuncia_fiscal=com_renuncia_fiscal, com_imune_isento=com_imune_isento,
        com_habilitado_beneficio=com_habilitado_beneficio,
        com_vinculo_politico=com_vinculo_politico, vinculo_fonte=vinculo_fonte,
        com_contrato_pncp=com_contrato_pncp, pncp_categoria=pncp_categoria,
        com_marca_registrada=com_marca_registrada,
        com_incentivo_estadual=com_incentivo_estadual, com_devedor_contumaz=com_devedor_contumaz, com_insolvencia=com_insolvencia, com_par_es=com_par_es, com_contrato_tcees=com_contrato_tcees, com_contrato_estadual_es=com_contrato_estadual_es,
        com_beneficio_fiscal=com_beneficio_fiscal, beneficio_tipo=beneficio_tipo,
        com_unidade_conservacao=com_unidade_conservacao,
        com_ambiental_proximidade=com_ambiental_proximidade,
        ambiental_proximidade_tipo=ambiental_proximidade_tipo,
        com_risco_geologico=com_risco_geologico,
        risco_geologico_grau=risco_geologico_grau,
        cnpj=cnpj, nivel_integridade=nivel_integridade,
        com_ocorrencia_socio=com_ocorrencia_socio, ocorrencia_fonte=ocorrencia_fonte,
        ocorrencia_criterio_forte=ocorrencia_criterio_forte,
        com_socio_estrangeiro=com_socio_estrangeiro, socio_estrangeiro_gafi=socio_estrangeiro_gafi,
        com_grupo_economico=com_grupo_economico, grupo_relacao=grupo_relacao,
        grupo_min_empresas=grupo_min_empresas, processo_validacao=processo_validacao,
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
def obter_empresa(cnpj: str, processo_polo: list = None, processo_classe: list = None,
                   sancao_tipo: list = None, sancao_orgao: str = None,
                   beneficio_tipo: list = None, vinculo_fonte: list = None,
                   pncp_categoria: list = None,
                   ambiental_proximidade_tipo: list = None, ctx: Context = None) -> dict:
    """Visão 360º de uma empresa pelo CNPJ (14 dígitos): dados cadastrais,
    sócios, complemento JUCEES, geolocalização, todas as pendências
    (processos, sanções, infrações ambientais, dívida ativa), vínculos
    políticos de sócios (PEP, candidaturas e doações no TSE), contratos com
    órgãos públicos (federais via Portal da Transparência e municipais/
    estaduais/federais via PNCP), benefícios/renúncias fiscais (renúncia
    fiscal por ano, imunidade/isenção de IRPJ, habilitação a regime de
    benefício), marcas registradas no INPI, Unidades de Conservação (se a
    empresa está DENTRO de alguma), proximidade a pontos ambientais
    (fiscalização/autuação, barragem, outorga hídrica — a até 500m) e setor
    de risco geológico/inundação (se a empresa está DENTRO de algum, Defesa
    Civil/CPRM/PMRR Serra-Viana), com um resumo agregado.

    Também traz (quando há dado):
    - avaliacao_integridade: nota de risco de integridade 0-100, nível e os
      fatores com fonte e motivo;
    - processos_descartados (homônimos fora da lista) e processos_socios
      (processos pessoais dos sócios, só por nome, tribunais do ES);
    - ocorrencias_socios: due diligence dos sócios (PGFN PF, servidor, CEAF,
      Bolsa Família, IBAMA, BCB, CVM, OFAC/ONU/UK, ICIJ...);
    - grupo_economico e risco_pais_socios (GAFI + IPC dos sócios estrangeiros);
    - redes_sociais: site confirmado (prova: Registro.br, CNPJ no site ou
      e-mail compatível), redes e WhatsApp publicados no site — dado provável;
    - devedor_contumaz_es: lista de devedores contumazes de ICMS da SEFAZ-ES;
    - insolvencia: recuperação judicial/falência (marcador da Receita na
      razão social + processos dessas classes, papel não identificado);
    - par_es: processos anticorrupção (PAR) do Governo do ES — SECONT;
    - contratos_tcees: contratos com prefeituras/órgãos do ES (TCEES, desde
      2021) e contratos_estaduais_es: contratos do Governo do ES (SEGER),
      cada um com qtd, valor_total e os 100 mais recentes;
    - dividas_ativas inclui FGTS e previdenciário (tipo_tributo "FGTS — ..." /
      "Previdenciário — ..."); beneficios_fiscais inclui COMPETE_ES e INVEST_ES.

    processo_polo (Réu/Autor/Terceiro/TODOS) e processo_classe filtram só a
    LISTA de processos devolvida; sancao_tipo/sancao_orgao filtram só a
    LISTA de sanções; beneficio_tipo filtra a LISTA de benefícios fiscais
    (RENUNCIA/IMUNE_ISENTO/HABILITADO/COMPETE_ES/INVEST_ES); vinculo_fonte filtra a
    LISTA de vínculos políticos (TSE_DOACAO/TSE_CANDIDATURA); pncp_categoria
    filtra a LISTA de contratos PNCP; ambiental_proximidade_tipo filtra a
    LISTA de proximidade ambiental (fiscalizacao/barragem/outorga) — todos
    (exceto sancao_orgao) aceitam string única OU lista, pra combinar mais
    de um valor (ex.: vinculo_fonte=["TSE_DOACAO","TSE_CANDIDATURA"] mostra
    os dois tipos de vínculo na lista). O resumo (contagens, valores totais
    em R$, tem_pendencia_juridica_ou_fiscal) sempre reflete o total real da
    empresa, sem esses filtros. Note que proximidade ambiental e setor de
    risco geológico NÃO contam como pendência jurídico-fiscal (são sinal de
    contexto, não de sanção).

    No servidor remoto (https://empresas.brunokobi.tech/mcp/) exige a chave
    de API da conta (cadastro grátis no site; envie em 'Authorization: Bearer
    gv_...' ou na URL '?chave=gv_...') e gasta 1 relatório da cota mensal —
    rever o mesmo CNPJ no mesmo mês não conta de novo. Rodando localmente
    (stdio), não há limite.

    Retorna {"erro": ...} se o CNPJ não estiver na base."""
    cnpj = "".join(ch for ch in str(cnpj) if ch.isdigit())
    uso = _cobrar_relatorio_mcp(ctx, cnpj)
    if uso is not None and not uso.get("ok"):
        return uso["bloqueio"]
    try:
        resultado = dataset_queries.obter_empresa(
            cnpj, processo_polo=processo_polo, processo_classe=processo_classe,
            sancao_tipo=sancao_tipo, sancao_orgao=sancao_orgao,
            beneficio_tipo=beneficio_tipo, vinculo_fonte=vinculo_fonte,
            pncp_categoria=pncp_categoria,
            ambiental_proximidade_tipo=ambiental_proximidade_tipo)
    except Exception:
        if uso is not None and uso.get("novo"):  # falhou depois de cobrar: devolve a cota
            contas.estornar(uso["usuario"], cnpj, uso["mes"])
        raise
    if resultado is None:
        return {"erro": f"CNPJ {cnpj} não encontrado na base."}
    if uso is not None:
        resultado["cota"] = {k: uso[k] for k in ("usados", "cota", "mes")}
    return resultado


def _requisicao_http(ctx):
    """Request HTTP do servidor remoto, ou None no uso local (stdio)."""
    try:
        return getattr(ctx.request_context, "request", None) if ctx is not None else None
    except (ValueError, LookupError, AttributeError):
        return None


def _cobrar_relatorio_mcp(ctx, cnpj: str):
    """None no uso local (sem cota). No remoto: {"ok": True, ...uso} ou
    {"ok": False, "bloqueio": {...}} com os dados básicos e a explicação."""
    req = _requisicao_http(ctx)
    if req is None or not contas.cadastro_ativo():
        return None
    basico = dataset_queries.dados_basicos_empresa(cnpj)
    if basico is None:
        return {"ok": False, "bloqueio": {"erro": f"CNPJ {cnpj} não encontrado na base."}}
    basico = {"cnpj": cnpj, **basico}
    usuario = contas.usuario_da_requisicao(req)
    if usuario is None:
        return {"ok": False, "bloqueio": {
            "erro": "chave_necessaria", "empresa": basico,
            "mensagem": "O relatório completo (visão 360º) pelo MCP remoto exige uma chave de API. "
                        "Cadastre-se grátis em https://empresas.brunokobi.tech (Google ou e-mail), gere a "
                        "chave em 'Minha conta' e configure o cliente MCP com o cabeçalho "
                        "'Authorization: Bearer gv_...' ou a URL https://empresas.brunokobi.tech/mcp/?chave=gv_... "
                        f"— {contas.COTA_MENSAL} relatórios por mês. As outras ferramentas (busca, estatísticas, "
                        "classificação) continuam livres."}}
    uso = contas.consumir(usuario, cnpj, "mcp")
    uso["usuario"] = usuario
    if not uso["ok"]:
        return {"ok": False, "bloqueio": {
            "erro": "cota_esgotada", "empresa": basico, "usados": uso["usados"], "cota": uso["cota"],
            "mensagem": f"A cota de {uso['cota']} relatórios de {uso['mes']} acabou; renova no dia 1º. "
                        "Relatórios já abertos neste mês continuam liberados. O limite evita abuso e sobrecarga "
                        "do servidor; o banco completo é público para download no GitHub do projeto, sem limite."}}
    return uso


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
      esse canal (pref_rede = site confirmado; pref_whatsapp = WhatsApp
      publicado no site da empresa).
    - portes: lista de códigos de porte alvo (pontua quem está na lista).
    - presenca: "com" | "sem" | "indiferente" (presença digital = site
      confirmado; "sem" quer dizer sem site confirmado, já que a coleta ainda
      não cobre todas as empresas).
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
