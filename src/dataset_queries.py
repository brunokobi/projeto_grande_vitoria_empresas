"""
Camada de consultas do dataset consolidado — usada tanto pelo servidor MCP
(mcp_server.py) quanto pela API REST (api.py), pra não duplicar SQL.

Todas as funções abrem o SQLite em modo somente-leitura e usam queries
parametrizadas (sem interpolação de input do usuário) para evitar injeção.
"""
import sqlite3
import unicodedata
from contextlib import contextmanager

import config


def _sem_acento(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()


@contextmanager
def _conn():
    # Modo read-only: a API/MCP nunca escrevem no banco.
    uri = f"file:{config.DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# Colunas de ordenação permitidas (whitelist — nunca vem direto do usuário).
_ORDENAR_POR = {
    "razao_social", "capital_social", "municipio", "porte", "cnpj",
}


def estatisticas() -> dict:
    """Panorama geral do dataset — totais e distribuições."""
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
        por_municipio = {
            r["municipio"]: r["n"]
            for r in conn.execute(
                "SELECT municipio, COUNT(*) n FROM empresas "
                "GROUP BY municipio ORDER BY n DESC"
            )
        }
        por_porte = {
            (r["porte"] or "(não informado)"): r["n"]
            for r in conn.execute(
                "SELECT porte, COUNT(*) n FROM empresas GROUP BY porte ORDER BY n DESC"
            )
        }
        por_regime = {
            (r["regime_tributario"] or "(não informado)"): r["n"]
            for r in conn.execute(
                "SELECT regime_tributario, COUNT(*) n FROM empresas "
                "GROUP BY regime_tributario ORDER BY n DESC"
            )
        }
        top_cnae = {
            r["cnae_principal"]: r["n"]
            for r in conn.execute(
                "SELECT cnae_principal, COUNT(*) n FROM empresas "
                "WHERE cnae_principal IS NOT NULL "
                "GROUP BY cnae_principal ORDER BY n DESC LIMIT 20"
            )
        }
        com_telefone = conn.execute(
            "SELECT COUNT(*) FROM empresas WHERE telefone IS NOT NULL AND telefone != ''"
        ).fetchone()[0]
        com_email = conn.execute(
            "SELECT COUNT(*) FROM empresas WHERE email IS NOT NULL AND email != ''"
        ).fetchone()[0]

        satelites = {}
        for tabela in ("processos_judiciais", "sancoes_administrativas",
                       "infracoes_ambientais", "dividas_ativas", "registros_jucees",
                       "socios", "enriquecimento_places"):
            satelites[tabela] = conn.execute(
                f"SELECT COUNT(*) FROM {tabela}"
            ).fetchone()[0]

    return {
        "total_empresas": total,
        "por_municipio": por_municipio,
        "por_porte": por_porte,
        "por_regime_tributario": por_regime,
        "top_20_cnae_principal": top_cnae,
        "empresas_com_telefone": com_telefone,
        "empresas_com_email": com_email,
        "registros_por_tabela": satelites,
    }


def buscar_empresas(
    municipio: str = None,
    cnae: str = None,
    porte: str = None,
    regime_tributario: str = None,
    texto: str = None,
    tem_pendencia: bool = None,
    com_telefone: bool = None,
    com_email: bool = None,
    capital_min: float = None,
    capital_max: float = None,
    ordenar_por: str = "razao_social",
    limite: int = 50,
    offset: int = 0,
) -> dict:
    """
    Busca empresas com filtros combináveis (todos opcionais). Retorna
    {'total': N, 'itens': [...]}. Pensada para prospecção: dá pra filtrar
    por município/CNAE/porte, exigir contato (telefone/e-mail) e excluir/
    exigir pendências jurídico-fiscais.
    """
    where = []
    params = []

    if municipio:
        where.append("municipio = ?")
        params.append(_sem_acento(municipio))
    if cnae:
        where.append("(cnae_principal = ? OR cnae_secundarios LIKE ?)")
        params.extend([cnae, f"%{cnae}%"])
    if porte:
        where.append("porte = ?")
        params.append(porte)
    if regime_tributario:
        where.append("regime_tributario = ?")
        params.append(regime_tributario)
    if texto:
        where.append("(razao_social LIKE ? OR nome_fantasia LIKE ?)")
        params.extend([f"%{texto}%", f"%{texto}%"])
    if com_telefone:
        where.append("telefone IS NOT NULL AND telefone != ''")
    if com_email:
        where.append("email IS NOT NULL AND email != ''")
    if capital_min is not None:
        where.append("capital_social >= ?")
        params.append(capital_min)
    if capital_max is not None:
        where.append("capital_social <= ?")
        params.append(capital_max)

    # Pendência jurídico-fiscal = existe registro em qualquer tabela satélite.
    pendencia_sql = (
        "(EXISTS (SELECT 1 FROM processos_judiciais p WHERE p.cnpj_empresa = e.cnpj) "
        "OR EXISTS (SELECT 1 FROM sancoes_administrativas s WHERE s.cnpj_empresa = e.cnpj) "
        "OR EXISTS (SELECT 1 FROM infracoes_ambientais i WHERE i.cnpj_empresa = e.cnpj) "
        "OR EXISTS (SELECT 1 FROM dividas_ativas d WHERE d.cnpj_empresa = e.cnpj))"
    )
    if tem_pendencia is True:
        where.append(pendencia_sql)
    elif tem_pendencia is False:
        where.append("NOT " + pendencia_sql)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    ordem = ordenar_por if ordenar_por in _ORDENAR_POR else "razao_social"
    limite = max(1, min(int(limite), 500))  # teto de 500 por página
    offset = max(0, int(offset))

    with _conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM empresas e{where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT cnpj, razao_social, nome_fantasia, cnae_principal, porte, "
            f"capital_social, municipio, bairro, telefone, email, regime_tributario "
            f"FROM empresas e{where_sql} ORDER BY {ordem} LIMIT ? OFFSET ?",
            params + [limite, offset],
        ).fetchall()

    return {
        "total": total,
        "limite": limite,
        "offset": offset,
        "itens": [dict(r) for r in rows],
    }


def obter_empresa(cnpj: str) -> dict:
    """Visão 360º de uma empresa pelo CNPJ (14 dígitos, só números)."""
    cnpj = "".join(c for c in str(cnpj) if c.isdigit())
    with _conn() as conn:
        empresa = conn.execute(
            "SELECT * FROM empresas WHERE cnpj = ?", (cnpj,)
        ).fetchone()
        if empresa is None:
            return None

        socios = [dict(r) for r in conn.execute(
            "SELECT nome_socio, cpf_parcial, qualificacao, data_entrada "
            "FROM socios WHERE cnpj_empresa = ?", (cnpj,)
        )]
        jucees = conn.execute(
            "SELECT * FROM registros_jucees WHERE cnpj_empresa = ?", (cnpj,)
        ).fetchone()
        processos = [dict(r) for r in conn.execute(
            "SELECT numero_processo, tribunal, classe, assunto, data_ultima_movimentacao "
            "FROM processos_judiciais WHERE cnpj_empresa = ? LIMIT 100", (cnpj,)
        )]
        sancoes = [dict(r) for r in conn.execute(
            "SELECT tipo, motivo, orgao_sancionador, data_inicio, data_fim "
            "FROM sancoes_administrativas WHERE cnpj_empresa = ? LIMIT 100", (cnpj,)
        )]
        ambiental = [dict(r) for r in conn.execute(
            "SELECT tipo_infracao, status, data_auto FROM infracoes_ambientais "
            "WHERE cnpj_empresa = ? LIMIT 100", (cnpj,)
        )]
        dividas = [dict(r) for r in conn.execute(
            "SELECT valor, situacao, data_inscricao FROM dividas_ativas "
            "WHERE cnpj_empresa = ? LIMIT 100", (cnpj,)
        )]
        geo = conn.execute(
            "SELECT latitude, longitude FROM enriquecimento_places WHERE cnpj_empresa = ?",
            (cnpj,),
        ).fetchone()

    valor_divida = sum(d["valor"] for d in dividas if d.get("valor"))
    return {
        "empresa": dict(empresa),
        "socios": socios,
        "jucees": dict(jucees) if jucees else None,
        "geolocalizacao": dict(geo) if geo else None,
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
            "tem_pendencia_juridica_ou_fiscal": bool(
                processos or sancoes or ambiental or dividas
            ),
        },
    }
