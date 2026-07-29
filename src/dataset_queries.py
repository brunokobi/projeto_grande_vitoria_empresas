"""
Camada de consultas do dataset consolidado — usada pelo servidor MCP
(mcp_server.py), pela API REST e pelo dashboard (api.py), pra não duplicar SQL.

Todas as funções abrem o SQLite em modo somente-leitura e usam queries
parametrizadas (sem interpolação de input do usuário) para evitar injeção.
"""
import json
import math
import re
import sqlite3
import unicodedata
from contextlib import contextmanager

import config

# Tabela CNAE (código de 7 dígitos -> descrição), extraída da base oficial
# da Receita Federal e versionada em reference/cnaes.json.
try:
    _CNAE = json.loads((config.BASE_DIR / "reference" / "cnaes.json").read_text(encoding="utf-8"))
except Exception:
    _CNAE = {}

# Situação cadastral (código da Receita -> nome).
_SITUACAO = {"01": "Nula", "02": "Ativa", "03": "Suspensa",
             "04": "Inapta", "08": "Baixada"}

# Qualificação do sócio (código -> nome), da base oficial da RF.
try:
    _QUALIF = json.loads((config.BASE_DIR / "reference" / "qualificacoes.json").read_text(encoding="utf-8"))
except Exception:
    _QUALIF = {}

# Faixa etária (código da RF -> descrição).
_FAIXA = {"0": "Não informada", "1": "0 a 12", "2": "13 a 20", "3": "21 a 30",
          "4": "31 a 40", "5": "41 a 50", "6": "51 a 60", "7": "61 a 70",
          "8": "71 a 80", "9": "acima de 80"}


def qualif_desc(codigo):
    return _QUALIF.get(str(codigo or "").strip())


def faixa_desc(codigo):
    return _FAIXA.get(str(codigo or "").strip())


def cnae_desc(codigo):
    return _CNAE.get(str(codigo or "").strip())


def situacao_desc(codigo):
    return _SITUACAO.get(str(codigo or "").strip())


def _sem_acento(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()


def _distancia_km(lat1, lon1, lat2, lon2):
    """Distância em linha reta (Haversine) entre dois pontos, em km. SQLite
    não tem função geoespacial nativa — registrada como função SQL custom
    (`distancia_km`) em cada conexão, ver _conn()."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0  # raio médio da Terra, km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@contextmanager
def _conn():
    uri = f"file:{config.DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    # mmap deixa o SO cachear o arquivo direto (evita cópia pra buffer do
    # SQLite a cada leitura); cache_size maior reduz I/O em consultas
    # repetidas — o banco só cresce (hoje ~65MB+) e é só leitura aqui.
    conn.execute("PRAGMA mmap_size = 268435456")  # 256MB
    conn.execute("PRAGMA cache_size = -20000")     # ~20MB de cache de página
    conn.create_function("distancia_km", 4, _distancia_km, deterministic=True)
    try:
        yield conn
    finally:
        conn.close()


def _tabela_existe(conn, nome: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)
    ).fetchone() is not None


def _fts_query(texto: str) -> str:
    """Converte texto livre numa query FTS5 (prefixo de cada palavra, AND
    implícito) — ex.: 'cyber suite' -> 'cyber* suite*'. Cada termo é escapado
    entre aspas duplas pra não quebrar com caractere especial do FTS5."""
    termos = re.findall(r"\w+", texto, flags=re.UNICODE)
    if not termos:
        return '""'
    return " ".join(f'"{t}"*' for t in termos)


# Colunas de ordenação permitidas (whitelist — nunca vem direto do usuário).
_ORDENAR_POR = {"razao_social", "capital_social", "municipio", "porte", "cnpj"}

# Expressão de pendência jurídico-fiscal (empresa tem registro em qualquer
# tabela satélite). Usada tanto como filtro quanto como coluna calculada.
_PENDENCIA_EXPR = (
    "(EXISTS (SELECT 1 FROM processos_judiciais p WHERE p.cnpj_empresa = e.cnpj) "
    "OR EXISTS (SELECT 1 FROM sancoes_administrativas s WHERE s.cnpj_empresa = e.cnpj) "
    "OR EXISTS (SELECT 1 FROM infracoes_ambientais i WHERE i.cnpj_empresa = e.cnpj) "
    "OR EXISTS (SELECT 1 FROM dividas_ativas d WHERE d.cnpj_empresa = e.cnpj))"
)


def _filtros_sql(*, tem_contato=False, tem_fts=False, tem_contratos=False,
                 tem_beneficios=False,
                 municipio=None, cnae=None, cnae_prefix=None,
                 porte=None, regime_tributario=None, texto=None, tem_pendencia=None,
                 com_telefone=None, com_email=None, com_whatsapp=None,
                 com_rede_social=None, capital_min=None, capital_max=None,
                 com_processos=None, com_sancoes=None, com_ambiental=None, com_divida=None,
                 com_trabalho_escravo=None, com_cepim=None, com_leniencia=None,
                 com_contratos_governamentais=None,
                 com_renuncia_fiscal=None, com_imune_isento=None, com_habilitado_beneficio=None,
                 socio=None):
    """Monta a cláusula WHERE (sobre o alias `e` = empresas) e os parâmetros."""
    where, params = [], []
    if municipio:
        where.append("e.municipio = ?")
        params.append(_sem_acento(municipio))
    if cnae:
        where.append("(e.cnae_principal = ? OR e.cnae_secundarios LIKE ?)")
        params.extend([cnae, f"%{cnae}%"])
    if cnae_prefix:
        where.append("e.cnae_principal LIKE ?")
        params.append(f"{cnae_prefix}%")
    if porte:
        where.append("e.porte = ?")
        params.append(porte)
    if regime_tributario:
        where.append("e.regime_tributario = ?")
        params.append(regime_tributario)
    if texto:
        if tem_fts:
            # FTS5: casa por PALAVRA (prefixo), não substring solto no meio
            # da palavra como o LIKE antigo — mais rápido (não varre a
            # tabela inteira) e já ignora acento (tokenizer remove_diacritics).
            where.append(
                "e.cnpj IN (SELECT cnpj FROM empresas_fts WHERE empresas_fts MATCH ?)"
            )
            params.append(_fts_query(texto))
        else:
            where.append("(e.razao_social LIKE ? OR e.nome_fantasia LIKE ?)")
            params.extend([f"%{texto}%", f"%{texto}%"])
    if socio:
        where.append("EXISTS (SELECT 1 FROM socios so WHERE so.cnpj_empresa = e.cnpj "
                     "AND so.nome_socio LIKE ?)")
        params.append(f"%{socio}%")
    if com_telefone:
        where.append("e.telefone IS NOT NULL AND e.telefone != ''")
    if com_email:
        where.append("e.email IS NOT NULL AND e.email != ''")
    if capital_min is not None:
        where.append("e.capital_social >= ?")
        params.append(capital_min)
    if capital_max is not None:
        where.append("e.capital_social <= ?")
        params.append(capital_max)
    if tem_pendencia is True:
        where.append(_PENDENCIA_EXPR)
    elif tem_pendencia is False:
        where.append("NOT " + _PENDENCIA_EXPR)
    # Filtros por tipo específico de pendência jurídico-fiscal.
    if com_processos:
        where.append("EXISTS (SELECT 1 FROM processos_judiciais p WHERE p.cnpj_empresa = e.cnpj)")
    if com_sancoes:
        where.append("EXISTS (SELECT 1 FROM sancoes_administrativas s WHERE s.cnpj_empresa = e.cnpj)")
    if com_ambiental:
        where.append("EXISTS (SELECT 1 FROM infracoes_ambientais i WHERE i.cnpj_empresa = e.cnpj)")
    if com_divida:
        where.append("EXISTS (SELECT 1 FROM dividas_ativas d WHERE d.cnpj_empresa = e.cnpj)")
    # Alertas de risco específicos (subtipos de sanção administrativa).
    if com_trabalho_escravo:
        where.append("EXISTS (SELECT 1 FROM sancoes_administrativas s WHERE s.cnpj_empresa = e.cnpj "
                     "AND s.tipo = 'TRABALHO_ESCRAVO')")
    if com_cepim:
        where.append("EXISTS (SELECT 1 FROM sancoes_administrativas s WHERE s.cnpj_empresa = e.cnpj "
                     "AND s.tipo = 'CEPIM')")
    if com_leniencia:
        where.append("EXISTS (SELECT 1 FROM sancoes_administrativas s WHERE s.cnpj_empresa = e.cnpj "
                     "AND s.tipo = 'LENIENCIA')")
    if com_contratos_governamentais:
        if not tem_contratos:
            where.append("0")  # tabela ainda não existe nesta cópia do dataset → sem resultados
        else:
            where.append("EXISTS (SELECT 1 FROM contratos_governamentais c WHERE c.cnpj_empresa = e.cnpj)")
    if com_renuncia_fiscal or com_imune_isento or com_habilitado_beneficio:
        if not tem_beneficios:
            where.append("0")  # tabela ainda não existe nesta cópia do dataset → sem resultados
        else:
            if com_renuncia_fiscal:
                where.append("EXISTS (SELECT 1 FROM beneficios_fiscais b WHERE b.cnpj_empresa = e.cnpj "
                             "AND b.tipo = 'RENUNCIA')")
            if com_imune_isento:
                where.append("EXISTS (SELECT 1 FROM beneficios_fiscais b WHERE b.cnpj_empresa = e.cnpj "
                             "AND b.tipo = 'IMUNE_ISENTO')")
            if com_habilitado_beneficio:
                where.append("EXISTS (SELECT 1 FROM beneficios_fiscais b WHERE b.cnpj_empresa = e.cnpj "
                             "AND b.tipo = 'HABILITADO')")
    if com_whatsapp or com_rede_social:
        if not tem_contato:
            where.append("0")  # etapa `contato` ainda não rodou → sem resultados
        else:
            if com_whatsapp:
                where.append("EXISTS (SELECT 1 FROM enriquecimento_contato ec "
                             "WHERE ec.cnpj_empresa = e.cnpj AND ec.whatsapp IS NOT NULL)")
            if com_rede_social:
                where.append("EXISTS (SELECT 1 FROM enriquecimento_contato ec "
                             "WHERE ec.cnpj_empresa = e.cnpj AND (ec.instagram IS NOT NULL "
                             "OR ec.facebook IS NOT NULL OR ec.linkedin IS NOT NULL))")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    return where_sql, params


def estatisticas() -> dict:
    """Panorama geral do dataset — totais e distribuições."""
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
        por_municipio = {r["municipio"]: r["n"] for r in conn.execute(
            "SELECT municipio, COUNT(*) n FROM empresas GROUP BY municipio ORDER BY n DESC")}
        por_porte = {(r["porte"] or "(n/d)"): r["n"] for r in conn.execute(
            "SELECT porte, COUNT(*) n FROM empresas GROUP BY porte ORDER BY n DESC")}
        por_regime = {(r["regime_tributario"] or "(n/d)"): r["n"] for r in conn.execute(
            "SELECT regime_tributario, COUNT(*) n FROM empresas GROUP BY regime_tributario ORDER BY n DESC")}
        com_telefone = conn.execute(
            "SELECT COUNT(*) FROM empresas WHERE telefone IS NOT NULL AND telefone != ''").fetchone()[0]
        com_email = conn.execute(
            "SELECT COUNT(*) FROM empresas WHERE email IS NOT NULL AND email != ''").fetchone()[0]
        com_pendencia = conn.execute(
            f"SELECT COUNT(*) FROM empresas e WHERE {_PENDENCIA_EXPR}").fetchone()[0]
        satelites = {}
        for tabela in ("processos_judiciais", "sancoes_administrativas",
                       "infracoes_ambientais", "dividas_ativas", "registros_jucees",
                       "socios", "enriquecimento_places"):
            satelites[tabela] = conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        if _tabela_existe(conn, "vinculos_politicos"):
            satelites["vinculos_politicos"] = conn.execute(
                "SELECT COUNT(*) FROM vinculos_politicos").fetchone()[0]
        if _tabela_existe(conn, "contratos_governamentais"):
            satelites["contratos_governamentais"] = conn.execute(
                "SELECT COUNT(*) FROM contratos_governamentais").fetchone()[0]
        if _tabela_existe(conn, "beneficios_fiscais"):
            satelites["beneficios_fiscais"] = conn.execute(
                "SELECT COUNT(*) FROM beneficios_fiscais").fetchone()[0]
    return {
        "total_empresas": total,
        "por_municipio": por_municipio,
        "por_porte": por_porte,
        "por_regime_tributario": por_regime,
        "empresas_com_telefone": com_telefone,
        "empresas_com_email": com_email,
        "empresas_com_pendencia": com_pendencia,
        "registros_por_tabela": satelites,
    }


def segmentos() -> list:
    """Lista de segmentos (divisão CNAE) com a contagem de empresas em cada,
    para popular o filtro de segmento do dashboard."""
    with _conn() as conn:
        contagem = {r["div"]: r["n"] for r in conn.execute(
            "SELECT substr(cnae_principal,1,2) div, COUNT(*) n FROM empresas "
            "WHERE cnae_principal IS NOT NULL GROUP BY div")}
    itens = [{"prefixo": p, "nome": nome, "total": contagem.get(p, 0)}
             for p, nome in config.SEGMENTOS_CNAE.items()]
    return sorted(itens, key=lambda x: x["total"], reverse=True)


def buscar_empresas(municipio=None, cnae=None, cnae_prefix=None, porte=None,
                    regime_tributario=None, texto=None, tem_pendencia=None,
                    com_telefone=None, com_email=None, com_whatsapp=None,
                    com_rede_social=None, capital_min=None, capital_max=None,
                    com_processos=None, com_sancoes=None, com_ambiental=None,
                    com_divida=None, com_trabalho_escravo=None, com_cepim=None,
                    com_leniencia=None, com_contratos_governamentais=None,
                    com_renuncia_fiscal=None, com_imune_isento=None,
                    com_habilitado_beneficio=None,
                    socio=None, ordenar_por="razao_social",
                    limite=50, offset=0) -> dict:
    """Busca empresas com filtros combináveis. Retorna {'total','itens',...}."""
    ordem = ordenar_por if ordenar_por in _ORDENAR_POR else "razao_social"
    limite = max(1, min(int(limite), 500))
    offset = max(0, int(offset))
    with _conn() as conn:
        tem_contato = _tabela_existe(conn, "enriquecimento_contato")
        tem_fts = _tabela_existe(conn, "empresas_fts")
        tem_contratos = _tabela_existe(conn, "contratos_governamentais")
        tem_beneficios = _tabela_existe(conn, "beneficios_fiscais")
        where_sql, params = _filtros_sql(
            tem_contato=tem_contato, tem_fts=tem_fts, tem_contratos=tem_contratos,
            tem_beneficios=tem_beneficios,
            municipio=municipio, cnae=cnae,
            cnae_prefix=cnae_prefix, porte=porte, regime_tributario=regime_tributario,
            texto=texto, tem_pendencia=tem_pendencia, com_telefone=com_telefone,
            com_email=com_email, com_whatsapp=com_whatsapp,
            com_rede_social=com_rede_social, capital_min=capital_min, capital_max=capital_max,
            com_processos=com_processos, com_sancoes=com_sancoes,
            com_ambiental=com_ambiental, com_divida=com_divida,
            com_trabalho_escravo=com_trabalho_escravo, com_cepim=com_cepim,
            com_leniencia=com_leniencia, com_contratos_governamentais=com_contratos_governamentais,
            com_renuncia_fiscal=com_renuncia_fiscal, com_imune_isento=com_imune_isento,
            com_habilitado_beneficio=com_habilitado_beneficio,
            socio=socio)
        total = conn.execute(f"SELECT COUNT(*) FROM empresas e{where_sql}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT e.cnpj, e.razao_social, e.nome_fantasia, e.cnae_principal, e.porte, "
            f"e.capital_social, e.municipio, e.bairro, e.telefone, e.email, e.regime_tributario, "
            f"{_PENDENCIA_EXPR} AS tem_pendencia "
            f"FROM empresas e{where_sql} ORDER BY e.{ordem} LIMIT ? OFFSET ?",
            params + [limite, offset]).fetchall()
    itens = []
    for r in rows:
        d = dict(r)
        d["cnae_desc"] = cnae_desc(d.get("cnae_principal"))
        itens.append(d)
    return {"total": total, "limite": limite, "offset": offset, "itens": itens}


def pontos_mapa(limite=20000, **filtros):
    """Empresas geocodificadas (lat/long) que batem nos filtros — para o mapa
    do dashboard. Retorna {'total', 'limite', 'pontos':[{cnpj,razao_social,
    nome_fantasia,municipio,lat,lng,tem_pendencia}]}. `total` é quantas batem
    (pode passar do limite; o mapa mostra até `limite`)."""
    filtros.pop("ordenar_por", None)
    limite = max(1, min(int(limite), 400000))
    with _conn() as conn:
        tem_contato = _tabela_existe(conn, "enriquecimento_contato")
        tem_fts = _tabela_existe(conn, "empresas_fts")
        tem_contratos = _tabela_existe(conn, "contratos_governamentais")
        tem_beneficios = _tabela_existe(conn, "beneficios_fiscais")
        where_sql, params = _filtros_sql(tem_contato=tem_contato, tem_fts=tem_fts,
                                          tem_contratos=tem_contratos,
                                          tem_beneficios=tem_beneficios, **filtros)
        cond = "ep.latitude IS NOT NULL"
        if where_sql:
            cond += " AND " + where_sql[len(" WHERE "):]
        base = ("FROM empresas e JOIN enriquecimento_places ep "
                "ON ep.cnpj_empresa = e.cnpj WHERE " + cond)
        total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT e.cnpj, e.razao_social, e.nome_fantasia, e.municipio, "
            f"ep.latitude AS lat, ep.longitude AS lng, {_PENDENCIA_EXPR} AS tem_pendencia "
            f"{base} LIMIT ?", params + [limite]).fetchall()
    return {"total": total, "limite": limite, "pontos": [dict(r) for r in rows]}


def buscar_por_raio(lat: float, lon: float, raio_km: float = 5, limite=50, offset=0, **filtros) -> dict:
    """Empresas geocodificadas dentro de um raio (km) de um ponto (lat, lon),
    ordenadas da mais próxima pra mais longe. Combina com os mesmos filtros
    de buscar_empresas (município, cnae, pendência, etc.) — passe como
    kwargs. Retorna {'total','centro','raio_km','limite','offset','itens':
    [... com distancia_km]}.

    Pra buscar perto de um ENDEREÇO (não coordenada), geocodifique primeiro
    (ver src/geocode.py) e use o lat/lon retornado aqui.
    """
    filtros.pop("ordenar_por", None)
    limite = max(1, min(int(limite), 500))
    offset = max(0, int(offset))
    raio_km = max(0.05, float(raio_km))
    lat, lon = float(lat), float(lon)
    # bounding box grosseiro (barato, comparação simples) antes do cálculo
    # exato de Haversine (roda em Python por linha) — evita rodar a função
    # pra tabela inteira quando o raio é pequeno frente ao total de empresas
    # geocodificadas.
    lat_delta = raio_km / 111.0
    lon_delta = raio_km / (111.0 * max(0.1, math.cos(math.radians(lat))))
    with _conn() as conn:
        tem_contato = _tabela_existe(conn, "enriquecimento_contato")
        tem_fts = _tabela_existe(conn, "empresas_fts")
        tem_contratos = _tabela_existe(conn, "contratos_governamentais")
        tem_beneficios = _tabela_existe(conn, "beneficios_fiscais")
        where_sql, params = _filtros_sql(tem_contato=tem_contato, tem_fts=tem_fts,
                                          tem_contratos=tem_contratos,
                                          tem_beneficios=tem_beneficios, **filtros)
        cond = ("ep.latitude BETWEEN ? AND ? AND ep.longitude BETWEEN ? AND ? "
                "AND distancia_km(?, ?, ep.latitude, ep.longitude) <= ?")
        cond_params = [lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta,
                       lat, lon, raio_km]
        if where_sql:
            cond += " AND " + where_sql[len(" WHERE "):]
        base = ("FROM empresas e JOIN enriquecimento_places ep "
                "ON ep.cnpj_empresa = e.cnpj WHERE " + cond)
        total = conn.execute(f"SELECT COUNT(*) {base}", cond_params + params).fetchone()[0]
        rows = conn.execute(
            f"SELECT e.cnpj, e.razao_social, e.nome_fantasia, e.cnae_principal, e.porte, "
            f"e.municipio, e.bairro, e.telefone, e.email, ep.latitude AS lat, ep.longitude AS lng, "
            f"distancia_km(?, ?, ep.latitude, ep.longitude) AS distancia_km, "
            f"{_PENDENCIA_EXPR} AS tem_pendencia "
            f"{base} ORDER BY distancia_km LIMIT ? OFFSET ?",
            [lat, lon] + cond_params + params + [limite, offset]).fetchall()
    itens = []
    for r in rows:
        d = dict(r)
        d["cnae_desc"] = cnae_desc(d.get("cnae_principal"))
        d["distancia_km"] = round(d["distancia_km"], 2)
        itens.append(d)
    return {"total": total, "limite": limite, "offset": offset,
            "centro": {"lat": lat, "lon": lon}, "raio_km": raio_km, "itens": itens}


def classificar_empresas(objetivo="generico", pref_telefone=None, pref_email=None,
                         pref_whatsapp=None, pref_rede=None, portes=None,
                         presenca="indiferente", fiscal="indiferente",
                         municipio=None, cnae_prefix=None, texto=None,
                         capital_min=None, capital_max=None, limite=50) -> dict:
    """Classifica/pontua empresas conforme um 'questionário' de prospecção.
    Cada critério ativo soma pontos; o score é normalizado 0-100 e recebe um
    rótulo (Quente/Morno/Frio). O peso é definido pelas respostas — o objetivo
    comercial ajusta o que conta como bom lead."""
    with _conn() as conn:
        tem_contato = _tabela_existe(conn, "enriquecimento_contato")
        tem_fts = _tabela_existe(conn, "empresas_fts")
        divida = "EXISTS (SELECT 1 FROM dividas_ativas d WHERE d.cnpj_empresa = e.cnpj)"
        tel = "(e.telefone IS NOT NULL AND e.telefone != '')"
        eml = "(e.email IS NOT NULL AND e.email != '')"
        if tem_contato:
            site = ("EXISTS (SELECT 1 FROM enriquecimento_contato ec WHERE ec.cnpj_empresa = e.cnpj "
                    "AND (ec.site IS NOT NULL OR ec.instagram IS NOT NULL OR ec.facebook IS NOT NULL OR ec.linkedin IS NOT NULL))")
            wpp = "EXISTS (SELECT 1 FROM enriquecimento_contato ec WHERE ec.cnpj_empresa = e.cnpj AND ec.whatsapp IS NOT NULL)"
        else:
            site, wpp = "0", "0"

        termos, score_params = [], []          # (expr, peso)
        if pref_telefone: termos.append((tel, 15))
        if pref_email: termos.append((eml, 15))
        if pref_whatsapp: termos.append((wpp, 15))
        if pref_rede: termos.append((site, 15))
        if portes:
            ph = ",".join("?" * len(portes))
            termos.append((f"e.porte IN ({ph})", 20)); score_params.extend(portes)
        if presenca == "com": termos.append((site, 20))
        elif presenca == "sem": termos.append((f"NOT {site}", 20))
        if fiscal == "limpas": termos.append((f"NOT {_PENDENCIA_EXPR}", 25))
        elif fiscal == "com_pendencia": termos.append((divida, 25))
        # Presets por objetivo comercial:
        if objetivo == "regularizacao": termos.append((divida, 30))
        elif objetivo == "marketing":
            termos.append((f"NOT {site}", 25)); termos.append((tel, 10))
        elif objetivo == "credito": termos.append((f"NOT {_PENDENCIA_EXPR}", 25))
        elif objetivo == "software":
            termos.append((site, 15)); termos.append(("e.capital_social >= 100000", 10))

        max_pts = sum(p for _, p in termos)
        score_sql = ("(" + " + ".join(f"CASE WHEN {e} THEN {p} ELSE 0 END" for e, p in termos) + ")") if termos else "0"

        where_sql, where_params = _filtros_sql(
            tem_contato=tem_contato, tem_fts=tem_fts, municipio=municipio, cnae_prefix=cnae_prefix,
            texto=texto, capital_min=capital_min, capital_max=capital_max)
        limite = max(1, min(int(limite), 500))
        rows = conn.execute(
            f"SELECT e.cnpj, e.razao_social, e.nome_fantasia, e.municipio, e.porte, "
            f"e.cnae_principal, e.capital_social, {_PENDENCIA_EXPR} AS tem_pendencia, "
            f"{score_sql} AS score FROM empresas e{where_sql} "
            f"ORDER BY score DESC, e.razao_social LIMIT ?",
            score_params + where_params + [limite]).fetchall()

    def rotular(pct):
        if pct >= 70: return "🔥 Quente (A)"
        if pct >= 40: return "🙂 Morno (B)"
        return "❄️ Frio (C)"

    itens = []
    for r in rows:
        d = dict(r)
        d["cnae_desc"] = cnae_desc(d.get("cnae_principal"))
        d["score_pct"] = round(d["score"] / max_pts * 100) if max_pts else 0
        d["classificacao"] = rotular(d["score_pct"])
        itens.append(d)
    return {"total": len(itens), "pontos_maximos": max_pts,
            "criterios_ativos": len(termos), "itens": itens}


def exportar_empresas(max_linhas=20000, **filtros) -> list:
    """Retorna TODAS as empresas que batem com os filtros (até max_linhas),
    com colunas úteis de prospecção incluindo contato/redes se disponíveis."""
    filtros.pop("limite", None); filtros.pop("offset", None)
    ordem = filtros.pop("ordenar_por", "razao_social")
    ordem = ordem if ordem in _ORDENAR_POR else "razao_social"
    with _conn() as conn:
        tem_contato = _tabela_existe(conn, "enriquecimento_contato")
        tem_fts = _tabela_existe(conn, "empresas_fts")
        tem_contratos = _tabela_existe(conn, "contratos_governamentais")
        tem_beneficios = _tabela_existe(conn, "beneficios_fiscais")
        where_sql, params = _filtros_sql(tem_contato=tem_contato, tem_fts=tem_fts,
                                          tem_contratos=tem_contratos,
                                          tem_beneficios=tem_beneficios, **filtros)
        if tem_contato:
            join = " LEFT JOIN enriquecimento_contato ec ON ec.cnpj_empresa = e.cnpj"
            cols_contato = "ec.whatsapp, ec.site, ec.instagram, ec.facebook, ec.linkedin"
        else:
            join = ""
            cols_contato = ("NULL AS whatsapp, NULL AS site, NULL AS instagram, "
                            "NULL AS facebook, NULL AS linkedin")
        sql = (f"SELECT e.cnpj, e.razao_social, e.nome_fantasia, e.municipio, e.bairro, "
               f"e.cnae_principal, e.porte, e.capital_social, e.regime_tributario, "
               f"e.telefone, e.email, {cols_contato}, "
               f"{_PENDENCIA_EXPR} AS tem_pendencia "
               f"FROM empresas e{join}{where_sql} ORDER BY e.{ordem} LIMIT ?")
        rows = conn.execute(sql, params + [int(max_linhas)]).fetchall()
    saida = []
    for r in rows:
        d = dict(r)
        d["cnae_desc"] = cnae_desc(d.get("cnae_principal"))
        saida.append(d)
    return saida


def obter_empresa(cnpj: str) -> dict:
    """Visão 360º de uma empresa pelo CNPJ (14 dígitos, só números)."""
    cnpj = "".join(c for c in str(cnpj) if c.isdigit())
    with _conn() as conn:
        empresa = conn.execute("SELECT * FROM empresas WHERE cnpj = ?", (cnpj,)).fetchone()
        if empresa is None:
            return None
        socios = []
        for r in conn.execute(
                "SELECT nome_socio, cpf_parcial, qualificacao, data_entrada, faixa_etaria "
                "FROM socios WHERE cnpj_empresa = ?", (cnpj,)):
            s = dict(r)
            s["qualificacao_desc"] = qualif_desc(s.get("qualificacao"))
            s["faixa_etaria_desc"] = faixa_desc(s.get("faixa_etaria"))
            # Rede de participações: outras empresas da base onde a MESMA
            # pessoa também é sócia. Exige CPF mascarado + NOME idênticos —
            # o CPF vem mascarado (só 6 dígitos do meio) e sozinho colide
            # entre pessoas diferentes; nome + CPF mascarado é discriminante.
            cpf = (s.get("cpf_parcial") or "").strip()
            nome = (s.get("nome_socio") or "").strip()
            outras = []
            if cpf and nome:
                outras = [dict(x) for x in conn.execute(
                    "SELECT DISTINCT s2.cnpj_empresa AS cnpj, e.razao_social "
                    "FROM socios s2 JOIN empresas e ON e.cnpj = s2.cnpj_empresa "
                    "WHERE s2.cpf_parcial = ? AND s2.nome_socio = ? "
                    "AND s2.cnpj_empresa != ? LIMIT 30",
                    (cpf, nome, cnpj))]
            s["outras_empresas"] = outras
            socios.append(s)
        jucees = conn.execute(
            "SELECT * FROM registros_jucees WHERE cnpj_empresa = ?", (cnpj,)).fetchone()
        processos = [dict(r) for r in conn.execute(
            "SELECT numero_processo, tribunal, classe, assunto, polo, status, "
            "data_ultima_movimentacao, match_confianca, nome_socio_vinculado "
            "FROM processos_judiciais WHERE cnpj_empresa = ? "
            "ORDER BY data_ultima_movimentacao DESC LIMIT 100", (cnpj,))]
        sancoes = [dict(r) for r in conn.execute(
            "SELECT tipo, motivo, orgao_sancionador, data_inicio, data_fim, "
            "fundamentacao, numero_processo, ano_processo, numero_deliberacao, ano_deliberacao, "
            "nome_socio_vinculado "
            "FROM sancoes_administrativas WHERE cnpj_empresa = ? LIMIT 100", (cnpj,))]
        ambiental = [dict(r) for r in conn.execute(
            "SELECT tipo_infracao, status, data_auto, valor_multa, gravidade, tipo_multa, "
            "numero_auto, municipio_infracao, uf_infracao, enquadramento "
            "FROM infracoes_ambientais WHERE cnpj_empresa = ? ORDER BY valor_multa DESC LIMIT 100", (cnpj,))]
        dividas = [dict(r) for r in conn.execute(
            "SELECT valor, situacao, data_inscricao, tipo_tributo, numero_inscricao, "
            "ajuizada, tipo_devedor, unidade_responsavel FROM dividas_ativas "
            "WHERE cnpj_empresa = ? ORDER BY valor DESC LIMIT 100", (cnpj,))]
        vinculos_politicos = []
        if _tabela_existe(conn, "vinculos_politicos"):
            vinculos_politicos = [dict(r) for r in conn.execute(
                "SELECT nome_socio_vinculado, fonte, cargo_ou_funcao, orgao_ou_partido, "
                "ano, situacao, detalhe FROM vinculos_politicos "
                "WHERE cnpj_empresa = ? LIMIT 100", (cnpj,))]
        contratos_governamentais = []
        if _tabela_existe(conn, "contratos_governamentais"):
            contratos_governamentais = [dict(r) for r in conn.execute(
                "SELECT numero_contrato, objeto, orgao_superior, orgao, modalidade_compra, "
                "situacao_contrato, data_assinatura, data_inicio_vigencia, data_fim_vigencia, "
                "valor_inicial, valor_final, mes_referencia FROM contratos_governamentais "
                "WHERE cnpj_empresa = ? ORDER BY data_assinatura DESC LIMIT 100", (cnpj,))]
        beneficios_fiscais = []
        if _tabela_existe(conn, "beneficios_fiscais"):
            beneficios_fiscais = [dict(r) for r in conn.execute(
                "SELECT tipo, ano, valor, tipo_entidade, beneficio_fiscal, base_legal, "
                "inicio_habilitacao, fim_habilitacao FROM beneficios_fiscais "
                "WHERE cnpj_empresa = ? ORDER BY ano DESC LIMIT 100", (cnpj,))]
        geo = conn.execute(
            "SELECT latitude, longitude FROM enriquecimento_places WHERE cnpj_empresa = ?",
            (cnpj,)).fetchone()
        contato = None
        if _tabela_existe(conn, "enriquecimento_contato"):
            contato = conn.execute(
                "SELECT whatsapp, site, instagram, facebook, linkedin "
                "FROM enriquecimento_contato WHERE cnpj_empresa = ?", (cnpj,)).fetchone()
    valor_divida = sum(d["valor"] for d in dividas if d.get("valor"))
    emp = dict(empresa)
    emp["cnae_principal_desc"] = cnae_desc(emp.get("cnae_principal"))
    emp["situacao_cadastral_desc"] = situacao_desc(emp.get("situacao_cadastral"))
    return {
        "empresa": emp,
        "socios": socios,
        "jucees": dict(jucees) if jucees else None,
        "geolocalizacao": dict(geo) if geo else None,
        "contato": dict(contato) if contato else None,
        "processos_judiciais": processos,
        "sancoes_administrativas": sancoes,
        "infracoes_ambientais": ambiental,
        "dividas_ativas": dividas,
        "vinculos_politicos": vinculos_politicos,
        "contratos_governamentais": contratos_governamentais,
        "beneficios_fiscais": beneficios_fiscais,
        "resumo": {
            "qtd_socios": len(socios),
            "qtd_processos": len(processos),
            "qtd_sancoes": len(sancoes),
            "qtd_infracoes_ambientais": len(ambiental),
            "qtd_dividas_ativas": len(dividas),
            "qtd_vinculos_politicos": len(vinculos_politicos),
            "qtd_contratos_governamentais": len(contratos_governamentais),
            "qtd_beneficios_fiscais": len(beneficios_fiscais),
            "valor_total_divida_ativa": valor_divida,
            "tem_pendencia_juridica_ou_fiscal": bool(processos or sancoes or ambiental or dividas),
        },
    }
