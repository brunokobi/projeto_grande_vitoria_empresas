"""
Detalhes de um processo judicial, sob demanda (quando o card abre no modal).

Duas fontes públicas oficiais do CNJ, consultadas pelo NÚMERO do processo (não
há cruzamento por nome aqui — o número identifica o processo sem ambiguidade):

  - DataJud (API Pública, CNJ): metadados por instância — grau, órgão julgador,
    data de ajuizamento, assuntos, sistema, e a lista de movimentações.
    Chave pública publicada pelo próprio CNJ em
    https://datajud-wiki.cnj.jus.br/api-publica/acesso (pode ser trocada pelo
    CNJ; sobrescreva com a variável DATAJUD_API_KEY).
  - DJEN (Comunicações processuais, CNJ/PJe): intimações publicadas — órgão,
    tipo, data, texto, destinatários (polo ativo/passivo) e advogados.

Os campos são repassados como a fonte entrega (só datas formatadas); nada é
inferido. Cache de 7 dias em data/cache_midia.db (mesmo arquivo do cache de
mídia, tabela própria) — o banco principal é somente leitura.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request

from src.midia import CACHE_DB

DATAJUD_KEY = (os.environ.get("DATAJUD_API_KEY")
               or "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==")
_UA = "grande-vitoria-empresas-dashboard/1.0 (detalhe de processo sob demanda)"
CACHE_DIAS = 7
_MAX_MOVS = 30
_MAX_COMUNICACOES = 10


def _req(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 30):
    h = {"User-Agent": _UA, **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def _iso(dt: str | None) -> str | None:
    """'20240826143346' ou '2026-07-28T02:55:05.000Z' → '2024-08-26' / '2026-07-28T02:55'."""
    if not dt:
        return None
    if re.fullmatch(r"\d{14}", dt):
        return f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}"
    return dt[:16]


_GRAU = {"G1": "1º grau", "G2": "2º grau", "JE": "Juizado Especial", "TR": "Turma Recursal",
         "SUP": "Tribunal Superior", "TRU": "Turma Regional de Uniformização"}


def datajud(numero: str, tribunal: str) -> list[dict] | None:
    alias = "api_publica_" + re.sub(r"[^a-z0-9-]", "", tribunal.lower())
    corpo = json.dumps({"query": {"match": {"numeroProcesso": numero}}, "size": 10}).encode()
    # O DataJud costuma levar 20-35 s por consulta — timeout folgado.
    d = _req(f"https://api-publica.datajud.cnj.jus.br/{alias}/_search", data=corpo,
             headers={"Authorization": f"APIKey {DATAJUD_KEY}", "Content-Type": "application/json"},
             timeout=75)
    if d is None:
        return None
    instancias = []
    for h in (d.get("hits") or {}).get("hits") or []:
        s = h.get("_source") or {}
        movs = sorted(s.get("movimentos") or [], key=lambda m: m.get("dataHora") or "", reverse=True)
        instancias.append({
            "grau": _GRAU.get(s.get("grau"), s.get("grau")),
            "orgao_julgador": (s.get("orgaoJulgador") or {}).get("nome"),
            "classe": (s.get("classe") or {}).get("nome"),
            "data_ajuizamento": _iso(s.get("dataAjuizamento")),
            "sistema": (s.get("sistema") or {}).get("nome"),
            "formato": (s.get("formato") or {}).get("nome"),
            "assuntos": [a.get("nome", "").strip() for a in s.get("assuntos") or [] if a.get("nome")],
            "atualizado_em": _iso(s.get("dataHoraUltimaAtualizacao")),
            "qtd_movimentos": len(movs),
            "movimentos": [{
                "data": _iso(m.get("dataHora")),
                "nome": m.get("nome"),
                "complementos": [c.get("nome") or c.get("descricao") for c in m.get("complementosTabelados") or []
                                 if c.get("nome") or c.get("descricao")],
            } for m in movs[:_MAX_MOVS]],
        })
    ordem = {"1º grau": 0, "Juizado Especial": 0, "2º grau": 1, "Turma Recursal": 1}
    instancias.sort(key=lambda i: ordem.get(i["grau"], 2))
    return instancias


def djen(numero: str) -> dict | None:
    url = "https://comunicaapi.pje.jus.br/api/v1/comunicacao?" + urllib.parse.urlencode(
        {"numeroProcesso": numero, "itensPorPagina": _MAX_COMUNICACOES, "pagina": 1})
    d = _req(url)
    if d is None:
        return None
    itens = []
    for x in d.get("items") or []:
        itens.append({
            "data": x.get("data_disponibilizacao"),
            "tipo": x.get("tipoComunicacao"),
            "documento": x.get("tipoDocumento"),
            "orgao": x.get("nomeOrgao"),
            "texto": re.sub(r"\s+", " ", x.get("texto") or "").strip(),
            "link": x.get("link") if (x.get("link") or "").startswith("https://") else None,
            "polo_ativo": [p.get("nome") for p in x.get("destinatarios") or [] if p.get("polo") == "A"],
            "polo_passivo": [p.get("nome") for p in x.get("destinatarios") or [] if p.get("polo") == "P"],
            "advogados": sorted({(a.get("advogado") or {}).get("nome") for a in x.get("destinatarioadvogados") or []
                                 if (a.get("advogado") or {}).get("nome")}),
        })
    # O DJEN publica uma comunicação por destinatário: o mesmo ato (data + texto)
    # aparece repetido. Junta as repetidas somando partes/advogados — nada é
    # descartado além da duplicata exata.
    unicos: dict = {}
    for it in itens:
        k = (it["data"], it["tipo"], it["orgao"], it["texto"])
        if k not in unicos:
            unicos[k] = it
            continue
        u = unicos[k]
        for campo in ("polo_ativo", "polo_passivo", "advogados"):
            u[campo] = list(dict.fromkeys(u[campo] + it[campo]))
        u["link"] = u["link"] or it["link"]
    itens = sorted(unicos.values(), key=lambda i: i["data"] or "", reverse=True)
    return {"total": d.get("count"), "qtd_lidas": len(d.get("items") or []), "itens": itens}


def _cache(numero, valor=None):
    try:
        c = sqlite3.connect(CACHE_DB, timeout=10)
        try:
            c.execute("CREATE TABLE IF NOT EXISTS processo_cache (numero TEXT PRIMARY KEY, "
                      "consultado_em REAL, resultado TEXT)")
            if valor is None:
                row = c.execute("SELECT consultado_em, resultado FROM processo_cache WHERE numero=?",
                                (numero,)).fetchone()
                if row and time.time() - row[0] <= CACHE_DIAS * 86400:
                    return json.loads(row[1])
                return None
            c.execute("INSERT OR REPLACE INTO processo_cache VALUES (?,?,?)",
                      (numero, time.time(), json.dumps(valor, ensure_ascii=False)))
            c.commit()
        finally:
            c.close()
    except sqlite3.Error:
        return None


def detalhes(numero: str, tribunal: str, fonte: str, forcar: bool = False) -> dict:
    """fonte = 'datajud' ou 'djen' — consultadas separadamente porque o DataJud
    é lento (~30 s) e o DJEN responde em ~1 s: o modal mostra cada uma ao chegar."""
    numero = re.sub(r"\D", "", numero or "")
    chave = f"{fonte}:{numero}"
    if not forcar:
        em_cache = _cache(chave)
        if em_cache is not None:
            em_cache["cache"] = True
            return em_cache
    dados = datajud(numero, tribunal) if fonte == "datajud" else djen(numero)
    res = {"numero": numero, "tribunal": tribunal, "fonte": fonte,
           "consultado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "cache": False, "disponivel": dados is not None, "dados": dados}
    if dados is not None:  # falha da API não vai pro cache
        _cache(chave, res)
    return res
