"""
Menções da empresa na mídia (busca sob demanda, com cache).

Fontes gratuitas e sem chave:
  - Google Notícias (RSS de busca)  — principal; manchete, veículo, data, link.
  - GDELT DOC 2.0 (artlist)         — complementar; notícias indexadas do mundo
    todo. Limite público de 1 requisição a cada 5 s — o módulo respeita isso com
    um throttle global e, se a API recusar/cair, segue só com o Google Notícias.

Não entra em lote no pipeline (367 mil empresas): roda quando alguém pede no
modal, e o resultado fica em cache (`data/cache_midia.db`, separado do banco
principal, que é somente-leitura e trocado inteiro pelo refresh_dataset.py).

Os termos de risco ("fraude", "operação", "lavagem"...) só DESTACAM a notícia
como possível menção negativa — é triagem de mídia adversa (adverse media,
GAFI/FATF), não conclusão: a manchete pode ser sobre homônimo ou citar a
empresa como vítima. Não entra na nota de integridade.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from pathlib import Path

import config

CACHE_DB = Path(config.DB_PATH).parent / "cache_midia.db"
CACHE_DIAS = 7
_UA = "grande-vitoria-empresas-dashboard/1.0 (monitoramento de midia sob demanda)"
_MAX_ITENS = 25

# Sufixos societários que atrapalham a busca exata ("ACME COMERCIO LTDA ME").
_SUFIXOS = {
    "LTDA", "LTDA.", "ME", "EPP", "EIRELI", "S/A", "S.A.", "SA", "S.A", "MEI",
    "SOCIEDADE", "LIMITADA", "EM", "RECUPERACAO", "JUDICIAL", "SLU", "SS",
}
_PALAVRAS_GENERICAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "&", "-"}

# Termos de mídia adversa (sem acento, minúsculo). Agrupados pra mostrar o motivo.
TERMOS_RISCO = {
    "corrupção/fraude": [
        "fraude", "fraudul", "corrupc", "propina", "superfatur", "desvio",
        "licitacao irregular", "direcionamento", "cartel", "conluio", "peculato",
        "improbidade", "lavagem", "sonegac", "estelionat", "golpe",
    ],
    "investigação/polícia": [
        "operacao", "policia federal", "pf deflagra", "mandado", "busca e apreensao",
        "investigad", "investigac", "inquerito", "denuncia", "denunciad", "preso",
        "prisao", "gaeco", "ministerio publico", "mpf", "mpes", "indiciad", "cpi",
    ],
    "trabalhista/ambiental": [
        "trabalho escravo", "analogo a escravo", "trabalho infantil", "crime ambiental",
        "poluic", "vazamento", "desmatamento", "multad", "autuad", "interdit",
        "embargad",
    ],
    "financeiro/judicial": [
        "recuperacao judicial", "falencia", "calote", "inadimpl", "condenad",
        "condenacao", "acao civil publica", "bloqueio de bens", "penhora", "reclamacoes",
        "procon",
    ],
}

_lock_gdelt = threading.Lock()
_ultima_gdelt = [0.0]


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


def termos_busca(razao_social: str | None, nome_fantasia: str | None) -> list[str]:
    """Nomes a buscar entre aspas: razão social sem sufixo societário e, se
    diferente e específico o bastante, o nome fantasia."""
    nomes = []
    for nome in (razao_social, nome_fantasia):
        if not nome:
            continue
        nome = re.sub(r"[\s.,-]+S\s*[./]?\s*A\.?\s*$", "", nome.strip().upper())  # "S A", "S/A", "S.A."
        toks = [t for t in re.split(r"\s+", nome.strip().upper()) if t]
        while toks and (toks[-1] in _SUFIXOS or toks[-1] in _PALAVRAS_GENERICAS):
            toks.pop()
        limpo = " ".join(toks).strip(" -.,")
        # nome curto/genérico demais vira ruído ("BAR", "MERCADO SILVA")
        if len(limpo) < 6 or len([t for t in toks if t not in _PALAVRAS_GENERICAS]) < 2 and len(limpo) < 10:
            continue
        if limpo and limpo not in nomes:
            nomes.append(limpo)
    return nomes[:2]


def classificar_risco(texto: str) -> list[str]:
    t = _sem_acento(texto)
    return [grupo for grupo, termos in TERMOS_RISCO.items()
            if any(re.search(r"\b" + re.escape(x), t) for x in termos)]


def _cita_nome(texto: str, nomes: list[str]) -> bool:
    t = _sem_acento(texto)
    return any(_sem_acento(n) in t for n in nomes)


def _get(url: str, timeout: int = 20) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def _limpar_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def buscar_google_noticias(nome: str, municipio: str | None = None) -> list[dict] | None:
    q = f'"{nome}"'
    if municipio and len(nome) < 14:
        # nome curto: amarra no município/ES pra reduzir homônimo de outro estado
        q += f' ("{municipio.title()}" OR "Espírito Santo")'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"})
    raw = _get(url)
    if raw is None:
        return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    itens = []
    for it in root.iter("item"):
        titulo = (it.findtext("title") or "").strip()
        fonte_el = it.find("source")
        veiculo = (fonte_el.text or "").strip() if fonte_el is not None else ""
        if veiculo and titulo.endswith(" - " + veiculo):
            titulo = titulo[: -len(veiculo) - 3]
        data = None
        try:
            data = parsedate_to_datetime(it.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            pass
        itens.append({
            "titulo": titulo, "veiculo": veiculo, "data": data,
            "link": (it.findtext("link") or "").strip(),
            "trecho": "", "fonte": "Google Notícias",
        })
    return itens


def buscar_gdelt(nome: str) -> list[dict] | None:
    params = {"query": f'"{nome}" sourcecountry:brazil', "mode": "artlist",
              "format": "json", "maxrecords": "25", "sort": "datedesc",
              "timespan": "12m"}
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
    with _lock_gdelt:
        espera = 6 - (time.time() - _ultima_gdelt[0])
        if espera > 0:
            time.sleep(espera)
        raw = _get(url, timeout=25)
        _ultima_gdelt[0] = time.time()
    if raw is None:
        return None
    try:
        dados = json.loads(raw)
    except ValueError:
        return None  # recusa de rate limit vem em texto puro
    itens = []
    for a in dados.get("articles") or []:
        d = a.get("seendate") or ""
        itens.append({
            "titulo": (a.get("title") or "").strip(),
            "veiculo": a.get("domain") or "",
            "data": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else None,
            "link": a.get("url") or "",
            "trecho": "", "fonte": "GDELT",
        })
    return itens


def _cache_conn() -> sqlite3.Connection:
    c = sqlite3.connect(CACHE_DB, timeout=10)
    c.execute("CREATE TABLE IF NOT EXISTS midia_cache ("
              "cnpj TEXT PRIMARY KEY, consultado_em REAL, resultado TEXT)")
    return c


def _ler_cache(cnpj: str) -> dict | None:
    try:
        with _cache_conn() as c:
            row = c.execute("SELECT consultado_em, resultado FROM midia_cache WHERE cnpj=?",
                            (cnpj,)).fetchone()
    except sqlite3.Error:
        return None
    if not row or time.time() - row[0] > CACHE_DIAS * 86400:
        return None
    return json.loads(row[1])


def _gravar_cache(cnpj: str, resultado: dict) -> None:
    try:
        with _cache_conn() as c:
            c.execute("INSERT OR REPLACE INTO midia_cache VALUES (?,?,?)",
                      (cnpj, time.time(), json.dumps(resultado, ensure_ascii=False)))
    except sqlite3.Error:
        pass


def mencoes(cnpj: str, razao_social: str | None, nome_fantasia: str | None,
            municipio: str | None, forcar: bool = False) -> dict:
    if not forcar:
        cache = _ler_cache(cnpj)
        if cache is not None:
            cache["cache"] = True
            return cache

    nomes = termos_busca(razao_social, nome_fantasia)
    resultado = {"cnpj": cnpj, "termos": nomes, "itens": [], "fontes": {},
                 "consultado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "cache": False, "qtd_possivel_risco": 0}
    if not nomes:
        resultado["aviso"] = "Nome muito curto ou genérico para buscar sem gerar homônimos."
        return resultado

    fontes = {"Google Notícias": lambda n: buscar_google_noticias(n, municipio),
              "GDELT": buscar_gdelt}
    # As duas fontes em paralelo (o GDELT sozinho pode levar ~30 s com o throttle).
    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = {f: pool.submit(lambda fn=fn: [fn(n) for n in nomes])
                   for f, fn in fontes.items()}
        respostas = {f: fut.result() for f, fut in futuros.items()}

    vistos: set[str] = set()
    falhas = 0
    for fonte in fontes:
        total = 0
        ok = False
        for itens in respostas[fonte]:
            if itens is None:
                continue
            ok = True
            for it in itens:
                chave = _sem_acento(it["titulo"])[:90]
                if not it["titulo"] or chave in vistos:
                    continue
                vistos.add(chave)
                texto = f'{it["titulo"]} {it["trecho"]}'
                it["riscos"] = classificar_risco(texto)
                it["cita_nome"] = _cita_nome(texto, nomes)
                resultado["itens"].append(it)
                total += 1
        resultado["fontes"][fonte] = total if ok else "indisponível"
        falhas += 0 if ok else 1

    # Mais relevante primeiro: cita o nome no título, depois mais recente.
    resultado["itens"].sort(key=lambda x: x["data"] or "", reverse=True)
    resultado["itens"].sort(key=lambda x: not x["cita_nome"])  # sort estável
    resultado["itens"] = resultado["itens"][:_MAX_ITENS]
    resultado["qtd_possivel_risco"] = sum(1 for x in resultado["itens"] if x["riscos"])
    if falhas < 2:  # não cacheia quando as duas fontes falharam
        _gravar_cache(cnpj, resultado)
    return resultado
