"""
Camada de consultas do dataset consolidado — usada pelo servidor MCP
(mcp_server.py), pela API REST e pelo dashboard (api.py), pra não duplicar SQL.

Todas as funções abrem o SQLite em modo somente-leitura e usam queries
parametrizadas (sem interpolação de input do usuário) para evitar injeção.
"""
import json
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


def cnae_desc(codigo):
    return _CNAE.get(str(codigo or "").strip())


def situacao_desc(codigo):
    return _SITUACAO.get(str(codigo or "").strip())


def _sem_acento(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()


@contextmanager
def _conn():
    uri = f"file:{config.DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _tabela_existe(conn, nome: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)
    ).fetchone() is not None


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


def _filtros_sql(*, tem_contato=False, municipio=None, cnae=None, cnae_prefix=None,
                 porte=None, regime_tributario=None, texto=None, tem_pendencia=None,
                 com_telefone=None, com_email=None, com_whatsapp=None,
                 com_rede_social=None, capital_min=None, capital_max=None):
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
        where.append("(e.razao_social LIKE ? OR e.nome_fantasia LIKE ?)")
        params.extend([f"%{texto}%", f"%{texto}%"])
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
                    ordenar_por="razao_social", limite=50, offset=0) -> dict:
    """Busca empresas com filtros combináveis. Retorna {'total','itens',...}."""
    ordem = ordenar_por if ordenar_por in _ORDENAR_POR else "razao_social"
    limite = max(1, min(int(limite), 500))
    offset = max(0, int(offset))
    with _conn() as conn:
        tem_contato = _tabela_existe(conn, "enriquecimento_contato")
        where_sql, params = _filtros_sql(
            tem_contato=tem_contato, municipio=municipio, cnae=cnae,
            cnae_prefix=cnae_prefix, porte=porte, regime_tributario=regime_tributario,
            texto=texto, tem_pendencia=tem_pendencia, com_telefone=com_telefone,
            com_email=com_email, com_whatsapp=com_whatsapp,
            com_rede_social=com_rede_social, capital_min=capital_min, capital_max=capital_max)
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


def exportar_empresas(max_linhas=20000, **filtros) -> list:
    """Retorna TODAS as empresas que batem com os filtros (até max_linhas),
    com colunas úteis de prospecção incluindo contato/redes se disponíveis."""
    filtros.pop("limite", None); filtros.pop("offset", None)
    ordem = filtros.pop("ordenar_por", "razao_social")
    ordem = ordem if ordem in _ORDENAR_POR else "razao_social"
    with _conn() as conn:
        tem_contato = _tabela_existe(conn, "enriquecimento_contato")
        where_sql, params = _filtros_sql(tem_contato=tem_contato, **filtros)
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
        socios = [dict(r) for r in conn.execute(
            "SELECT nome_socio, cpf_parcial, qualificacao, data_entrada "
            "FROM socios WHERE cnpj_empresa = ?", (cnpj,))]
        jucees = conn.execute(
            "SELECT * FROM registros_jucees WHERE cnpj_empresa = ?", (cnpj,)).fetchone()
        processos = [dict(r) for r in conn.execute(
            "SELECT numero_processo, tribunal, classe, assunto, data_ultima_movimentacao "
            "FROM processos_judiciais WHERE cnpj_empresa = ? LIMIT 100", (cnpj,))]
        sancoes = [dict(r) for r in conn.execute(
            "SELECT tipo, motivo, orgao_sancionador, data_inicio, data_fim "
            "FROM sancoes_administrativas WHERE cnpj_empresa = ? LIMIT 100", (cnpj,))]
        ambiental = [dict(r) for r in conn.execute(
            "SELECT tipo_infracao, status, data_auto FROM infracoes_ambientais "
            "WHERE cnpj_empresa = ? LIMIT 100", (cnpj,))]
        dividas = [dict(r) for r in conn.execute(
            "SELECT valor, situacao, data_inscricao, tipo_tributo, numero_inscricao, "
            "ajuizada, tipo_devedor, unidade_responsavel FROM dividas_ativas "
            "WHERE cnpj_empresa = ? ORDER BY valor DESC LIMIT 100", (cnpj,))]
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
        "resumo": {
            "qtd_socios": len(socios),
            "qtd_processos": len(processos),
            "qtd_sancoes": len(sancoes),
            "qtd_infracoes_ambientais": len(ambiental),
            "qtd_dividas_ativas": len(dividas),
            "valor_total_divida_ativa": valor_divida,
            "tem_pendencia_juridica_ou_fiscal": bool(processos or sancoes or ambiental or dividas),
        },
    }
