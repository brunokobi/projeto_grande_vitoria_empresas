"""
Páginas públicas indexáveis (SEO): uma por empresa, por cidade, por cidade +
atividade (CNAE) e por cidade + bairro, mais o sitemap dividido.

Geradas no servidor a partir do banco somente-leitura (mesmo `_conn()` do
`dataset_queries`), com cache em memória que se renova quando o
`refresh_dataset.py` troca o arquivo do banco.

Regras de conteúdo (decididas em 20/11/2026, ver docs/PLANOS.md):
- Só dado cadastral neutro da Receita: nome, CNPJ, situação, porte, regime,
  atividades, endereço. Processos, dívidas, sanções, sócios, contratos e nota
  de integridade NÃO entram aqui — ficam no relatório completo, com login
  (fora do Google: evita exposição indevida e ações por dano moral).
- MEI (empresa individual, nome e endereço da pessoa física): só bairro e
  município, sem logradouro, número, CEP, coordenadas ou contato.
- Telefone e e-mail não aparecem em nenhuma página indexável.
- Remoção a pedido: CNPJs listados em `data/seo_remocoes.txt` (um por linha,
  fora do git) respondem 410 e saem do sitemap.
- Páginas de atividade/bairro com poucas empresas ficam `noindex` e fora do
  sitemap (conteúdo raso prejudica o site inteiro no Google).
- Sitemap de empresas (26/11/2026): só as que não são MEI, das maiores para as
  menores (porte, depois capital social), em blocos de 10 mil. Com ~380 mil
  URLs de uma vez o Search Console deixou ~376 mil como "detectada, mas não
  indexada"; as páginas de MEI (~200 mil, quase iguais entre si) continuam no
  ar e acessíveis pelas listas de cidade/atividade/bairro, só não são
  oferecidas no sitemap.
"""
import json
import os
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime
from html import escape

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import config
from src import dataset_queries

router = APIRouter()

SITE_URL = (os.environ.get("SITE_URL") or "https://empresas.brunokobi.tech").rstrip("/")
POR_PAGINA = 100
URLS_POR_SITEMAP = 10000
MIN_EMPRESAS_ATIVIDADE = 3   # abaixo disso: noindex e fora do sitemap
MIN_EMPRESAS_BAIRRO = 5
REMOCOES_PATH = config.BASE_DIR / "data" / "seo_remocoes.txt"

CIDADES = {  # slug -> (valor na coluna municipio, nome de exibição)
    "vitoria": ("VITORIA", "Vitória"),
    "vila-velha": ("VILA VELHA", "Vila Velha"),
    "serra": ("SERRA", "Serra"),
    "cariacica": ("CARIACICA", "Cariacica"),
    "viana": ("VIANA", "Viana"),
    "guarapari": ("GUARAPARI", "Guarapari"),
    "fundao": ("FUNDAO", "Fundão"),
}
_CIDADE_POR_MUNICIPIO = {m: (slug, nome) for slug, (m, nome) in CIDADES.items()}
_PORTE = {"01": "Microempresa (ME)", "03": "Empresa de pequeno porte (EPP)", "05": "Demais (médio e grande porte)"}
_PORTE_CURTO = {"01": "ME", "03": "EPP", "05": "Médio/grande"}


# ---------------------------------------------------------------- utilidades

def slugify(texto: str, limite: int = 80) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:limite].rstrip("-") or "empresa"


def _nome_slug(razao: str, fantasia: str) -> str:
    # Razão social de MEI começa com a raiz do CNPJ ("61.688.357 FULANO"): fora do slug.
    base = re.sub(r"^[\d.\s]+", "", razao or "") or (fantasia or "")
    return slugify(base)


def url_empresa(cnpj: str, razao: str, fantasia: str = None) -> str:
    return f"/empresa/{cnpj}-{_nome_slug(razao, fantasia)}"


def _fmt_cnpj(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c or "") == 14 else (c or "")


def _fmt_cep(c: str) -> str:
    c = re.sub(r"\D", "", c or "")
    return f"{c[:5]}-{c[5:]}" if len(c) == 8 else c


def _fmt_data(d: str) -> str:
    d = re.sub(r"\D", "", d or "")
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else ""


def _fmt_brl(v) -> str:
    try:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return ""


_MINUSCULAS = {"de", "da", "do", "das", "dos", "e"}


def titulo(texto: str) -> str:
    """BAIRRO JARDIM DA PENHA -> Jardim da Penha."""
    palavras = (texto or "").strip().lower().split()
    return " ".join(p if (i and p in _MINUSCULAS) else p[:1].upper() + p[1:] for i, p in enumerate(palavras))


def _versao_banco() -> float:
    try:
        return os.stat(config.DB_PATH).st_mtime
    except OSError:
        return 0.0


_cache = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 3000


def _em_cache(chave, gerar):
    """Cache em memória invalidado quando o arquivo do banco muda."""
    versao = _versao_banco()
    with _cache_lock:
        item = _cache.get(chave)
        if item and item[0] == versao:
            return item[1]
    valor = gerar()
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            for k in list(_cache)[: _CACHE_MAX // 4]:
                _cache.pop(k, None)
        _cache[chave] = (versao, valor)
    return valor


def _remocoes() -> set:
    def ler():
        try:
            return {re.sub(r"\D", "", l) for l in REMOCOES_PATH.read_text().splitlines() if re.sub(r"\D", "", l)}
        except OSError:
            return set()
    return _em_cache(("remocoes", _mtime(REMOCOES_PATH)), ler)


def _mtime(p) -> float:
    try:
        return os.stat(p).st_mtime
    except OSError:
        return 0.0


def _data_banco() -> str:
    return datetime.fromtimestamp(_versao_banco()).strftime("%Y-%m-%d") if _versao_banco() else ""


# ---------------------------------------------------------------- consultas (agregados por cidade)

def _agregados_cidade(municipio: str) -> dict:
    def gerar():
        with dataset_queries._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM empresas WHERE municipio = ?", (municipio,)).fetchone()[0]
            ativ = c.execute("SELECT cnae_principal, COUNT(*) n FROM empresas WHERE municipio = ? "
                             "AND cnae_principal IS NOT NULL GROUP BY 1 ORDER BY n DESC", (municipio,)).fetchall()
            bairros = c.execute("SELECT bairro, COUNT(*) n FROM empresas WHERE municipio = ? AND bairro IS NOT NULL "
                                "AND TRIM(bairro) <> '' GROUP BY 1 ORDER BY n DESC", (municipio,)).fetchall()
            portes = dict(c.execute("SELECT porte, COUNT(*) FROM empresas WHERE municipio = ? GROUP BY 1",
                                    (municipio,)).fetchall())
            mei = c.execute("SELECT COUNT(*) FROM empresas WHERE municipio = ? AND regime_tributario = 'MEI'",
                            (municipio,)).fetchone()[0]
        # Mesmo bairro com grafias diferentes na Receita ("ENSEADA DO SUA" e
        # "ENSEADA DO SUÁ"): agrupa pelo slug, exibe a grafia mais comum.
        bairro_por_slug = {}
        for b, n in bairros:
            nome_b, total_b, variantes = bairro_por_slug.get(slugify(b), (b, 0, []))
            if not nome_b.isascii() or b.isascii():
                pass
            else:
                nome_b = b  # prefere a grafia com acento
            bairro_por_slug[slugify(b)] = (nome_b, total_b + n, variantes + [b])
        bairros = sorted(((v[0], v[1]) for v in bairro_por_slug.values()), key=lambda x: -x[1])
        return {"total": total, "atividades": [(a, n) for a, n in ativ], "bairros": [(b, n) for b, n in bairros],
                "bairro_por_slug": bairro_por_slug, "portes": portes, "mei": mei}
    return _em_cache(("agg", municipio), gerar)


def _limpar_nomes(d: dict) -> dict:
    """Razão social/fantasia da Receita às vezes vêm com espaço no início ou duplo."""
    for k in ("razao_social", "nome_fantasia"):
        if d.get(k) is not None:
            d[k] = " ".join(d[k].split()) or None
    return d


def _listar(where: str, params: tuple, pagina: int):
    with dataset_queries._conn() as c:
        total = c.execute(f"SELECT COUNT(*) FROM empresas e WHERE {where}", params).fetchone()[0]
        linhas = c.execute(
            f"SELECT cnpj, razao_social, nome_fantasia, bairro, porte, regime_tributario, cnae_principal "
            f"FROM empresas e WHERE {where} ORDER BY porte DESC, capital_social DESC, razao_social "
            f"LIMIT ? OFFSET ?", params + (POR_PAGINA, (pagina - 1) * POR_PAGINA)).fetchall()
    removidos = _remocoes()
    return total, [_limpar_nomes(dict(r)) for r in linhas if r["cnpj"] not in removidos]


# ---------------------------------------------------------------- idiomas

IDIOMAS = ("pt", "en", "es")
_HTML_LANG = {"pt": "pt-BR", "en": "en", "es": "es"}
_OG_LOCALE = {"pt": "pt_BR", "en": "en_US", "es": "es_ES"}
# prefixo, "cidade", "atividade", "bairro" em cada idioma
_ROTAS = {"pt": ("", "cidade", "atividade", "bairro"),
          "en": ("/en", "city", "activity", "neighborhood"),
          "es": ("/es", "ciudad", "actividad", "barrio")}

_CNAE_TRAD = {}
for _l in ("en", "es"):
    try:
        _CNAE_TRAD[_l] = json.loads((config.BASE_DIR / "reference" / f"cnaes_{_l}.json").read_text(encoding="utf-8"))
    except Exception:
        _CNAE_TRAD[_l] = {}


def cnae_desc(cod: str, lang: str = "pt"):
    if lang != "pt" and _CNAE_TRAD.get(lang, {}).get(cod):
        return _CNAE_TRAD[lang][cod]
    return dataset_queries.cnae_desc(cod)


def p_cidade(lang: str, cidade: str) -> str:
    pre, cid, _, _ = _ROTAS[lang]
    return f"{pre}/{cid}/{cidade}"


def p_atividade(lang: str, cidade: str, cod: str) -> str:
    return f"{p_cidade(lang, cidade)}/{_ROTAS[lang][2]}/{cod}-{slugify(cnae_desc(cod, lang) or cod, 60)}"


def p_bairro(lang: str, cidade: str, bairro_slug: str) -> str:
    return f"{p_cidade(lang, cidade)}/{_ROTAS[lang][3]}/{bairro_slug}"


T = {
    "pt": {
        "nav_busca": "Busca e mapa", "nav_cidades": "Cidades", "nav_apoiar": "Apoiar", "inicio": "Início",
        "rodape_cidades": "Empresas por cidade", "rodape_fonte": "Dados públicos da Receita Federal, atualizados periodicamente{base}. Confira na fonte oficial antes de decidir.",
        "rodape_base": " (base de {d})", "privacidade": "Política de privacidade", "remocao": "Solicitar correção ou remoção",
        "aviso_idioma": "",
        "th_empresa": "Empresa", "th_atividade": "Atividade", "th_bairro": "Bairro", "th_porte": "Porte",
        "porte": {"01": "ME", "03": "EPP", "05": "Médio/grande"}, "nenhuma": "Nenhuma empresa nesta página.",
        "anteriores": "← Anteriores", "proximas": "Próximas →", "pagina_de": "Página {p} de {t}", "pagina_n": " — página {p}",
        "cid_h1": "Empresas em {c} (ES)",
        "cid_sub": "{t} empresas ativas: {mei} MEI, {me} microempresas (incluindo os MEI), {epp} de pequeno porte e {gr} de médio e grande porte.",
        "cid_cta": "Busque por nome, sócio, atividade ou pendência, veja todas no mapa e abra o relatório completo de cada empresa.",
        "cid_btn": "Abrir a busca e o mapa", "cid_h2_ativ": "Empresas por atividade em {c}", "cid_h2_bairro": "Empresas por bairro em {c}",
        "cid_title": "Empresas em {c} (ES): {t} empresas ativas por atividade e bairro",
        "cid_meta": "{t} empresas ativas em {c} (ES) por atividade e bairro: comércio, serviços, indústria e construção. Dados públicos da Receita Federal, com mapa e relatório por CNPJ.",
        "at_h1": "{a} em {c} (ES)",
        "at_sub": "{t} {emp} {ativa} com esta atividade principal (CNAE {cod}), das maiores para as menores.", "emp": ("empresa", "empresas"), "ativa": ("ativa", "ativas"),
        "at_outras": "A mesma atividade em outras cidades:", "at_title": "{a} em {c} (ES): {t} {emp}",
        "at_meta": "Lista de {t} empresas de {a_min} em {c} (ES), com CNPJ, bairro e porte. Dados públicos da Receita Federal.",
        "ba_h1": "Empresas no bairro {b}, {c} (ES)", "ba_sub": "{t} empresas ativas no bairro, das maiores para as menores.",
        "ba_h2_top": "Atividades mais comuns no bairro", "ba_h2_emp": "Empresas", "ba_trilha": "Bairro {b}",
        "ba_title": "Empresas no bairro {b}, {c} (ES): {t} empresas",
        "ba_meta": "{t} empresas ativas no bairro {b}, em {c} (ES): comércio, serviços e indústria, com CNPJ e atividade.",
        "e404_cidade": "Cidade fora da Grande Vitória.", "e404_ativ": "Atividade inválida.", "e404_cnae": "Código CNAE desconhecido.",
        "e404_sem": "Nenhuma empresa ativa com esta atividade em {c}.", "e404_pag": "Página fora do intervalo.", "e404_bairro": "Bairro não encontrado em {c}.",
    },
    "en": {
        "nav_busca": "Search & map", "nav_cidades": "Cities", "nav_apoiar": "Support", "inicio": "Home",
        "rodape_cidades": "Companies by city", "rodape_fonte": "Public data from Brazil's Federal Revenue Service (Receita Federal), updated periodically{base}. Check the official source before deciding.",
        "rodape_base": " (data as of {d})", "privacidade": "Privacy policy (Portuguese)", "remocao": "Request correction or removal",
        "aviso_idioma": "Company names, addresses and registry records are shown as registered in Brazil, in Portuguese. Company pages and the full report are in Portuguese.",
        "th_empresa": "Company", "th_atividade": "Activity", "th_bairro": "Neighborhood", "th_porte": "Size",
        "porte": {"01": "Micro", "03": "Small", "05": "Medium/large"}, "nenhuma": "No companies on this page.",
        "anteriores": "← Previous", "proximas": "Next →", "pagina_de": "Page {p} of {t}", "pagina_n": " — page {p}",
        "cid_h1": "Companies in {c}, Espírito Santo, Brazil",
        "cid_sub": "{t} active companies: {mei} individual microentrepreneurs (MEI), {me} micro companies (including MEI), {epp} small companies and {gr} medium and large companies.",
        "cid_cta": "Search by name, partner, activity or legal/tax record, see every company on the map and open the full report (in Portuguese).",
        "cid_btn": "Open search and map", "cid_h2_ativ": "Companies by activity in {c}", "cid_h2_bairro": "Companies by neighborhood in {c}",
        "cid_title": "Companies in {c} (ES, Brazil): {t} active companies by activity and neighborhood",
        "cid_meta": "{t} active companies in {c}, Espírito Santo, Brazil, by activity and neighborhood: retail, services, industry and construction. Public data from the Brazilian Federal Revenue Service.",
        "at_h1": "{a} in {c} (ES, Brazil)",
        "at_sub": "{t} active {emp} with this main activity (CNAE {cod}), largest first.", "emp": ("company", "companies"), "ativa": ("", ""),
        "at_outras": "The same activity in other cities:", "at_title": "{a} in {c} (ES, Brazil): {t} {emp}",
        "at_meta": "List of {t} companies — {a_min} — in {c}, Espírito Santo, Brazil, with CNPJ (tax ID), neighborhood and size. Public data.",
        "ba_h1": "Companies in {b}, {c} (ES, Brazil)", "ba_sub": "{t} active companies in the neighborhood, largest first.",
        "ba_h2_top": "Most common activities in the neighborhood", "ba_h2_emp": "Companies", "ba_trilha": "{b}",
        "ba_title": "Companies in {b}, {c} (ES, Brazil): {t} companies",
        "ba_meta": "{t} active companies in the {b} neighborhood of {c}, Espírito Santo, Brazil: retail, services and industry, with CNPJ and activity.",
        "e404_cidade": "City outside Greater Vitória.", "e404_ativ": "Invalid activity.", "e404_cnae": "Unknown CNAE code.",
        "e404_sem": "No active company with this activity in {c}.", "e404_pag": "Page out of range.", "e404_bairro": "Neighborhood not found in {c}.",
    },
    "es": {
        "nav_busca": "Búsqueda y mapa", "nav_cidades": "Ciudades", "nav_apoiar": "Apoyar", "inicio": "Inicio",
        "rodape_cidades": "Empresas por ciudad", "rodape_fonte": "Datos públicos de la Receita Federal de Brasil, actualizados periódicamente{base}. Verifique en la fuente oficial antes de decidir.",
        "rodape_base": " (base del {d})", "privacidade": "Política de privacidad (en portugués)", "remocao": "Solicitar corrección o eliminación",
        "aviso_idioma": "Los nombres, direcciones y registros de las empresas se muestran como están registrados en Brasil, en portugués. Las páginas de cada empresa y el informe completo están en portugués.",
        "th_empresa": "Empresa", "th_atividade": "Actividad", "th_bairro": "Barrio", "th_porte": "Tamaño",
        "porte": {"01": "Micro", "03": "Pequeña", "05": "Mediana/grande"}, "nenhuma": "No hay empresas en esta página.",
        "anteriores": "← Anteriores", "proximas": "Siguientes →", "pagina_de": "Página {p} de {t}", "pagina_n": " — página {p}",
        "cid_h1": "Empresas en {c}, Espírito Santo, Brasil",
        "cid_sub": "{t} empresas activas: {mei} microemprendedores individuales (MEI), {me} microempresas (incluidos los MEI), {epp} pequeñas empresas y {gr} medianas y grandes.",
        "cid_cta": "Busque por nombre, socio, actividad o antecedente legal/fiscal, vea todas en el mapa y abra el informe completo (en portugués).",
        "cid_btn": "Abrir la búsqueda y el mapa", "cid_h2_ativ": "Empresas por actividad en {c}", "cid_h2_bairro": "Empresas por barrio en {c}",
        "cid_title": "Empresas en {c} (ES, Brasil): {t} empresas activas por actividad y barrio",
        "cid_meta": "{t} empresas activas en {c}, Espírito Santo, Brasil, por actividad y barrio: comercio, servicios, industria y construcción. Datos públicos de la Receita Federal.",
        "at_h1": "{a} en {c} (ES, Brasil)",
        "at_sub": "{t} {emp} {ativa} con esta actividad principal (CNAE {cod}), de mayor a menor.", "emp": ("empresa", "empresas"), "ativa": ("activa", "activas"),
        "at_outras": "La misma actividad en otras ciudades:", "at_title": "{a} en {c} (ES, Brasil): {t} {emp}",
        "at_meta": "Lista de {t} empresas — {a_min} — en {c}, Espírito Santo, Brasil, con CNPJ, barrio y tamaño. Datos públicos.",
        "ba_h1": "Empresas en el barrio {b}, {c} (ES, Brasil)", "ba_sub": "{t} empresas activas en el barrio, de mayor a menor.",
        "ba_h2_top": "Actividades más comunes en el barrio", "ba_h2_emp": "Empresas", "ba_trilha": "Barrio {b}",
        "ba_title": "Empresas en el barrio {b}, {c} (ES, Brasil): {t} empresas",
        "ba_meta": "{t} empresas activas en el barrio {b} de {c}, Espírito Santo, Brasil: comercio, servicios e industria, con CNPJ y actividad.",
        "e404_cidade": "Ciudad fuera de la Gran Vitória.", "e404_ativ": "Actividad inválida.", "e404_cnae": "Código CNAE desconocido.",
        "e404_sem": "Ninguna empresa activa con esta actividad en {c}.", "e404_pag": "Página fuera de rango.", "e404_bairro": "Barrio no encontrado en {c}.",
    },
}


def _n(x, lang: str = "pt") -> str:
    s = f"{int(x or 0):,}"
    return s if lang == "en" else s.replace(",", ".")


def _data_local(lang: str) -> str:
    d = _data_banco()
    if not d:
        return ""
    a, m, dia = d.split("-")
    return f"{m}/{dia}/{a}" if lang == "en" else f"{dia}/{m}/{a}"


# ---------------------------------------------------------------- layout

_CSS = """
:root{--bg:#04060a;--panel:#0d1117;--line:#21262d;--text:#e6edf3;--muted:#9aa4ae;--green:#00ff88;--green-dim:#12b866;--green-deep:#0a3d28}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);
font-family:'Segoe UI',system-ui,-apple-system,Roboto,sans-serif;font-size:15px;line-height:1.55}
a{color:var(--green)}header{border-bottom:1px solid var(--line);padding:12px 16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
header .logo{font-family:'Courier New',monospace;font-weight:700;color:var(--green);text-decoration:none;letter-spacing:1px}
header nav{margin-left:auto;display:flex;gap:14px;flex-wrap:wrap;font-size:13px}
main{max-width:980px;margin:0 auto;padding:18px 16px 40px}
.trilha{font-size:12.5px;color:var(--muted);margin-bottom:6px}.trilha a{color:var(--muted)}
h1{font-size:26px;line-height:1.25;margin:4px 0 4px}h2{font-size:17px;color:var(--green);margin:28px 0 10px;letter-spacing:.3px}
.sub{color:var(--muted);margin:0 0 14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}
dl{display:grid;grid-template-columns:minmax(120px,210px) 1fr;gap:6px 14px;margin:0}dt{color:var(--muted)}dd{margin:0;word-break:break-word}
.cta{background:linear-gradient(160deg,#0d1f17,var(--panel));border-color:var(--green-dim)}
.btn{display:inline-block;background:var(--green-deep);color:var(--green);border:1px solid var(--green-dim);border-radius:8px;
padding:10px 16px;font-weight:600;text-decoration:none;margin-top:6px}.btn:hover{background:var(--green-dim);color:#04060a}
ul.lista{list-style:none;padding:0;margin:0;columns:2;column-gap:24px}ul.lista li{break-inside:avoid;padding:3px 0}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12.5px}.n{color:var(--muted);font-size:12.5px}
.pag{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.nota{font-size:12.5px;color:var(--muted)}
iframe.mapa{width:100%;height:260px;border:1px solid var(--line);border-radius:10px}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:12.5px;text-align:center;padding:18px 16px 28px}
@media(max-width:640px){h1{font-size:21px}dl{grid-template-columns:1fr}dt{margin-top:6px}ul.lista{columns:1}
th:nth-child(3),td:nth-child(3){display:none}}
"""


def _pagina(titulo_pag: str, descricao: str, canonica: str, corpo: str, trilha: list = None,
            jsonld: list = None, indexar: bool = True, status: int = 200, lang: str = "pt",
            alternativas: dict = None) -> HTMLResponse:
    """`alternativas` = {lang: caminho} da mesma página nos outros idiomas (hreflang)."""
    t = T[lang]
    trilha = trilha or []
    trilha_html = " › ".join(f'<a href="{escape(u)}">{escape(x)}</a>' if u else escape(x) for x, u in trilha)
    blocos = list(jsonld or [])
    if trilha:
        blocos.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": x, **({"item": SITE_URL + u} if u else {})}
            for i, (x, u) in enumerate(trilha)]})
    ld = "".join('<script type="application/ld+json">' + json.dumps(b, ensure_ascii=False).replace("</", "<\\/")
                 + "</script>" for b in blocos)
    hreflang = ""
    seletor = ""
    if alternativas:
        hreflang = "".join(f'<link rel="alternate" hreflang="{_HTML_LANG[l]}" href="{escape(SITE_URL + u)}">'
                           for l, u in alternativas.items())
        hreflang += f'<link rel="alternate" hreflang="x-default" href="{escape(SITE_URL + alternativas["pt"])}">'
        seletor = " ".join(f'<a href="{escape(u)}" hreflang="{_HTML_LANG[l]}"' + (' style="font-weight:700"' if l == lang else "")
                           + f'>{l.upper()}</a>' for l, u in alternativas.items())
    cidades = " · ".join(f'<a href="{p_cidade(lang, s)}">{escape(n)}</a>' for s, (_, n) in CIDADES.items())
    base = t["rodape_base"].format(d=_data_local(lang)) if _data_banco() else ""
    aviso = f'<p class="nota">{escape(t["aviso_idioma"])}</p>' if t["aviso_idioma"] else ""
    html = f"""<!doctype html><html lang="{_HTML_LANG[lang]}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='88'>🏢</text></svg>">
<title>{escape(titulo_pag)}</title><meta name="description" content="{escape(descricao)}">
<link rel="canonical" href="{escape(SITE_URL + canonica)}">{hreflang}
{'' if indexar else '<meta name="robots" content="noindex,follow">'}
<meta property="og:type" content="website"><meta property="og:title" content="{escape(titulo_pag)}">
<meta property="og:description" content="{escape(descricao)}"><meta property="og:url" content="{escape(SITE_URL + canonica)}">
<meta property="og:image" content="{SITE_URL}/og-image.png"><meta property="og:locale" content="{_OG_LOCALE[lang]}">
{_adsense(status)}<style>{_CSS}</style>{ld}</head><body>
<header><a class="logo" href="/">EMPRESAS · GRANDE VITÓRIA</a>
<nav><a href="/">{t["nav_busca"]}</a><a href="{p_cidade(lang, "vitoria")}">{t["nav_cidades"]}</a><a href="/#apoiar">{t["nav_apoiar"]}</a>{f'<span class="n">{seletor}</span>' if seletor else ''}</nav></header>
<main>{f'<div class="trilha">{trilha_html}</div>' if trilha else ''}{corpo}{aviso}</main>
<footer>{t["rodape_cidades"]}: {cidades}<br>
{escape(t["rodape_fonte"].format(base=base))}<br>
<a href="/#privacidade">{t["privacidade"]}</a> ·
<a href="mailto:brunokobi2@hotmail.com?subject=LGPD%20-%20pedido%20do%20titular">{t["remocao"]}</a> ·
© 2026 Bruno Kobi</footer></body></html>"""
    return HTMLResponse(html, status_code=status,
                        headers={"Cache-Control": "public, max-age=3600"} if status == 200 else None)


def _adsense(status: int) -> str:
    """Anúncios automáticos do AdSense, só em página pública com conteúdo (200)."""
    if not config.ADSENSE_CLIENT or status != 200:
        return ""
    from src import contas
    return contas.html_adsense()  # assinante com plano em dia não vê anúncio


def _cidade_ou_404(slug: str, lang: str = "pt"):
    if slug not in CIDADES:
        raise HTTPException(404, T[lang]["e404_cidade"])
    return CIDADES[slug]


def _tabela_empresas(linhas: list, mostrar_atividade: bool = True, mostrar_bairro: bool = True, lang: str = "pt") -> str:
    t = T[lang]
    if not linhas:
        return f'<p class="nota">{t["nenhuma"]}</p>'
    cab = f"<tr><th>{t['th_empresa']}</th>" + (f"<th>{t['th_atividade']}</th>" if mostrar_atividade else "") + \
          (f"<th>{t['th_bairro']}</th>" if mostrar_bairro else "") + f"<th>{t['th_porte']}</th></tr>"
    linhas_html = []
    for r in linhas:
        nome = r["nome_fantasia"] or r["razao_social"]
        sub = f'<div class="n">{escape(r["razao_social"])}</div>' if r["nome_fantasia"] else ""
        porte = "MEI" if r["regime_tributario"] == "MEI" else t["porte"].get(r["porte"], "")
        linhas_html.append(
            f'<tr><td><a href="{url_empresa(r["cnpj"], r["razao_social"], r["nome_fantasia"])}"'
            + ('' if lang == "pt" else ' hreflang="pt-BR"') + f'>{escape(nome)}</a>{sub}</td>'
            + (f'<td>{escape(cnae_desc(r["cnae_principal"], lang) or "")}</td>' if mostrar_atividade else "")
            + (f'<td>{escape(titulo(r["bairro"] or ""))}</td>' if mostrar_bairro else "")
            + f'<td class="n">{porte}</td></tr>')
    return f"<table>{cab}{''.join(linhas_html)}</table>"


def _paginacao(base: str, pagina: int, total: int, lang: str = "pt") -> str:
    t = T[lang]
    paginas = max(1, -(-total // POR_PAGINA))
    if paginas == 1:
        return ""
    ant = f'<a class="btn" href="{base}{"" if pagina == 2 else f"?pagina={pagina - 1}"}">{t["anteriores"]}</a>' if pagina > 1 else ""
    prox = f'<a class="btn" href="{base}?pagina={pagina + 1}">{t["proximas"]}</a>' if pagina < paginas else ""
    return f'<div class="pag">{ant}<span class="nota" style="align-self:center">{t["pagina_de"].format(p=pagina, t=paginas)}</span>{prox}</div>'


def _cta_relatorio(cnpj: str) -> str:
    return f"""<div class="card cta"><b>Relatório completo desta empresa</b>
<p style="margin:6px 0">Processos judiciais, dívida ativa, sanções, sócios e grupo econômico, contratos públicos,
benefícios fiscais e a nota de risco de integridade, cruzados a partir de fontes públicas oficiais.
Grátis com cadastro (Google ou e-mail): 10 relatórios por mês.</p>
<a class="btn" href="/?empresa={cnpj}" rel="nofollow">Ver relatório completo</a></div>"""


# ---------------------------------------------------------------- empresa

@router.get("/empresa/{chave}", include_in_schema=False)
def pagina_empresa(chave: str):
    m = re.match(r"^(\d{14})(?:-([a-z0-9-]*))?$", chave)
    if not m:
        raise HTTPException(404, "Página não encontrada.")
    cnpj = m.group(1)
    if cnpj in _remocoes():
        return _pagina("Página removida", "Página removida a pedido.", f"/empresa/{cnpj}",
                       "<h1>Página removida</h1><p>Esta página foi removida a pedido do titular.</p>",
                       indexar=False, status=410)
    with dataset_queries._conn() as c:
        e = c.execute("SELECT * FROM empresas WHERE cnpj = ?", (cnpj,)).fetchone()
        geo = c.execute("SELECT latitude, longitude FROM enriquecimento_places WHERE cnpj_empresa = ?",
                        (cnpj,)).fetchone() if e else None
    if e is None:
        raise HTTPException(404, "CNPJ não encontrado entre as empresas ativas da Grande Vitória.")
    e = _limpar_nomes(dict(e))
    canonica = url_empresa(cnpj, e["razao_social"], e["nome_fantasia"])
    if f"/empresa/{chave}" != canonica:
        return RedirectResponse(canonica, status_code=301)

    cid_slug, cid_nome = _CIDADE_POR_MUNICIPIO.get(e["municipio"], (None, titulo(e["municipio"] or "")))
    mei = e["regime_tributario"] == "MEI"
    nome = e["nome_fantasia"] or e["razao_social"]
    ativ = dataset_queries.cnae_desc(e["cnae_principal"]) or ""
    bairro = titulo(e["bairro"] or "")
    bairro_slug = slugify(e["bairro"]) if e["bairro"] else None

    def link_ativ(cod):
        desc = dataset_queries.cnae_desc(cod) or cod
        return (f'<a href="/cidade/{cid_slug}/atividade/{cod}-{slugify(desc, 60)}">{escape(desc)}</a>'
                if cid_slug else escape(desc)) + f' <span class="n">({cod[:4]}-{cod[4:5]}/{cod[5:]})</span>'

    secundarias = [s.strip() for s in (e["cnae_secundarios"] or "").split(",") if s.strip()]
    if mei:
        endereco = f"{escape(bairro)}, {escape(cid_nome)}/ES" if bairro else f"{escape(cid_nome)}/ES"
        nota_end = '<div class="nota">Endereço completo omitido: é um microempreendedor individual (MEI), e o endereço costuma ser a residência do titular.</div>'
    else:
        partes = [p for p in [titulo(e["logradouro"] or ""), e["numero"] or ""] if p]
        endereco = escape(", ".join(partes)) + (f" — {escape(bairro)}" if bairro else "") + \
            f", {escape(cid_nome)}/ES" + (f", CEP {_fmt_cep(e['cep'])}" if e["cep"] else "")
        nota_end = ""

    dados = [
        ("CNPJ", f'<span style="font-family:monospace">{_fmt_cnpj(cnpj)}</span>'),
        ("Razão social", escape(e["razao_social"] or "")),
        ("Nome fantasia", escape(e["nome_fantasia"] or "—")),
        ("Situação cadastral", "Ativa" + (f" desde {_fmt_data(e['data_situacao'])}" if _fmt_data(e["data_situacao"]) else "")),
        ("Porte", "Microempreendedor individual (MEI)" if mei else escape(_PORTE.get(e["porte"], "—"))),
        ("Regime tributário", escape(e["regime_tributario"] or "—")),
        ("Capital social", _fmt_brl(e["capital_social"]) or "—"),
        ("Atividade principal", link_ativ(e["cnae_principal"]) if e["cnae_principal"] else "—"),
        ("Endereço", endereco + nota_end),
    ]
    dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in dados)
    sec_html = ""
    if secundarias:
        sec_html = "<h2>Atividades secundárias</h2><div class='card'><ul class='lista'>" + \
            "".join(f"<li>{link_ativ(s)}</li>" for s in secundarias[:40]) + "</ul></div>"

    mapa = ""
    if not mei and geo and geo["latitude"] and geo["longitude"]:
        lat, lon = float(geo["latitude"]), float(geo["longitude"])
        bbox = f"{lon - .006},{lat - .004},{lon + .006},{lat + .004}"
        mapa = (f'<h2>Localização</h2><iframe class="mapa" loading="lazy" title="Mapa" '
                f'src="https://www.openstreetmap.org/export/embed.html?bbox={bbox}&amp;layer=mapnik&amp;marker={lat},{lon}"></iframe>'
                f'<div class="nota">Posição aproximada, geocodificada a partir do endereço da Receita. © colaboradores do OpenStreetMap.</div>')

    # Empresas do mesmo ramo no mesmo bairro (ou cidade), para navegação e contexto.
    with dataset_queries._conn() as c:
        vizinhas = [dict(r) for r in c.execute(
            "SELECT cnpj, razao_social, nome_fantasia, bairro, porte, regime_tributario, cnae_principal FROM empresas "
            "WHERE municipio = ? AND cnae_principal = ? AND cnpj <> ? "
            "ORDER BY (bairro = ?) DESC, porte DESC, capital_social DESC LIMIT 12",
            (e["municipio"], e["cnae_principal"], cnpj, e["bairro"]))]
    removidos = _remocoes()
    vizinhas = [_limpar_nomes(v) for v in vizinhas if v["cnpj"] not in removidos]
    viz_html = ""
    if vizinhas:
        viz_html = (f"<h2>Outras empresas de {escape(ativ.lower() or 'mesma atividade')} em {escape(cid_nome)}</h2>"
                    + _tabela_empresas(vizinhas, mostrar_atividade=False))

    links_ctx = []
    if cid_slug and bairro_slug:
        links_ctx.append(f'<a href="/cidade/{cid_slug}/bairro/{bairro_slug}">Empresas no bairro {escape(bairro)}</a>')
    if cid_slug:
        links_ctx.append(f'<a href="/cidade/{cid_slug}">Empresas em {escape(cid_nome)}</a>')

    corpo = f"""<h1>{escape(nome)}</h1>
<p class="sub">{'' if not e['nome_fantasia'] else escape(e['razao_social']) + ' · '}CNPJ {_fmt_cnpj(cnpj)} · {escape(ativ)}{f' · {escape(bairro)}' if bairro else ''}, {escape(cid_nome)}/ES</p>
<div class="card"><dl>{dl}</dl></div>
{_cta_relatorio(cnpj)}
{sec_html}{mapa}{viz_html}
<p class="nota" style="margin-top:22px">{' · '.join(links_ctx)}</p>
<p class="nota">Dados cadastrais da Receita Federal (base pública do CNPJ). Erro ou pedido de remoção:
<a href="mailto:brunokobi2@hotmail.com?subject={escape('LGPD - pedido do titular - CNPJ ' + cnpj)}">brunokobi2@hotmail.com</a> (resposta em até 15 dias).</p>"""

    org = {"@context": "https://schema.org", "@type": "Organization", "name": nome,
           "legalName": e["razao_social"], "taxID": _fmt_cnpj(cnpj), "url": SITE_URL + canonica,
           "address": {"@type": "PostalAddress", "addressLocality": cid_nome, "addressRegion": "ES",
                       "addressCountry": "BR", **({} if mei else {
                           "streetAddress": ", ".join(p for p in [titulo(e["logradouro"] or ""), e["numero"] or ""] if p),
                           "postalCode": _fmt_cep(e["cep"])})}}
    if _fmt_data(e["data_situacao"]):
        d = re.sub(r"\D", "", e["data_situacao"])
        org["foundingDate"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    if not mei and geo and geo["latitude"]:
        org["location"] = {"@type": "Place", "geo": {"@type": "GeoCoordinates",
                                                     "latitude": geo["latitude"], "longitude": geo["longitude"]}}
    trilha = [("Início", "/")]
    if cid_slug:
        trilha.append((cid_nome, f"/cidade/{cid_slug}"))
        if e["cnae_principal"]:
            trilha.append((ativ or e["cnae_principal"], f"/cidade/{cid_slug}/atividade/{e['cnae_principal']}-{slugify(ativ, 60)}"))
    trilha.append((nome, None))
    desc = (f"{nome}, CNPJ {_fmt_cnpj(cnpj)}: {ativ} em {bairro + ', ' if bairro else ''}{cid_nome}/ES. "
            f"Situação ativa, porte, regime tributário, atividades e endereço. Relatório completo com processos e dívidas.")
    return _pagina(f"{nome} — CNPJ {_fmt_cnpj(cnpj)} · {cid_nome}/ES", desc[:300], canonica, corpo,
                   trilha=trilha, jsonld=[org])


# ---------------------------------------------------------------- cidade, atividade e bairro (pt, en, es)

def _qs(pagina: int) -> str:
    return f"?pagina={pagina}" if pagina > 1 else ""


def _pagina_cidade(lang: str, cidade: str):
    municipio, nome = _cidade_ou_404(cidade, lang)
    t = T[lang]

    def gerar():
        a = _agregados_cidade(municipio)
        p = a["portes"]
        ativs = [(cod, n) for cod, n in a["atividades"] if n >= MIN_EMPRESAS_ATIVIDADE]
        bairros = [(b, n) for b, n in a["bairros"] if n >= MIN_EMPRESAS_BAIRRO]
        li_ativ = "".join(
            f'<li><a href="{p_atividade(lang, cidade, cod)}">{escape(cnae_desc(cod, lang) or cod)}</a> '
            f'<span class="n">{_n(n, lang)}</span></li>' for cod, n in ativs)
        li_bairro = "".join(
            f'<li><a href="{p_bairro(lang, cidade, slugify(b))}">{escape(titulo(b))}</a> <span class="n">{_n(n, lang)}</span></li>'
            for b, n in bairros)
        total = _n(a["total"], lang)
        sub = t["cid_sub"].format(t=total, mei=_n(a["mei"], lang), me=_n(p.get("01"), lang),
                                  epp=_n(p.get("03"), lang), gr=_n(p.get("05"), lang))
        corpo = f"""<h1>{escape(t["cid_h1"].format(c=nome))}</h1>
<p class="sub">{escape(sub)}</p>
<div class="card cta">{escape(t["cid_cta"])}<br><a class="btn" href="/">{t["cid_btn"]}</a></div>
<h2>{escape(t["cid_h2_ativ"].format(c=nome))}</h2><div class="card"><ul class="lista">{li_ativ}</ul></div>
<h2>{escape(t["cid_h2_bairro"].format(c=nome))}</h2><div class="card"><ul class="lista">{li_bairro}</ul></div>"""
        alt = {l: p_cidade(l, cidade) for l in IDIOMAS}
        return _pagina(t["cid_title"].format(c=nome, t=total), t["cid_meta"].format(c=nome, t=total),
                       p_cidade(lang, cidade), corpo, trilha=[(t["inicio"], "/"), (nome, None)],
                       lang=lang, alternativas=alt)
    return _em_cache(("cidade", lang, cidade), gerar)


def _pagina_atividade(lang: str, cidade: str, chave: str, pagina: int):
    municipio, nome = _cidade_ou_404(cidade, lang)
    t = T[lang]
    m = re.match(r"^(\d{7})(?:-[a-z0-9-]*)?$", chave)
    if not m:
        raise HTTPException(404, t["e404_ativ"])
    cod = m.group(1)
    desc = cnae_desc(cod, lang)
    if not desc:
        raise HTTPException(404, t["e404_cnae"])
    base = p_atividade(lang, cidade, cod)
    if f"{p_cidade(lang, cidade)}/{_ROTAS[lang][2]}/{chave}" != base:
        return RedirectResponse(base + _qs(pagina), status_code=301)

    def gerar():
        total, linhas = _listar("municipio = ? AND cnae_principal = ?", (municipio, cod), pagina)
        if total == 0:
            raise HTTPException(404, t["e404_sem"].format(c=nome))
        if linhas == [] and pagina > 1:
            raise HTTPException(404, t["e404_pag"])
        outras = " · ".join(f'<a href="{p_atividade(lang, s, cod)}">{escape(n)}</a>'
                            for s, (_, n) in CIDADES.items() if s != cidade)
        n_fmt = _n(total, lang)
        cod_fmt = f"{cod[:4]}-{cod[4:5]}/{cod[5:]}"
        corpo = f"""<h1>{escape(t["at_h1"].format(a=desc, c=nome))}</h1>
<p class="sub">{escape(t["at_sub"].format(t=n_fmt, cod=cod_fmt, emp=t["emp"][total != 1], ativa=t["ativa"][total != 1]))}</p>
{_tabela_empresas(linhas, mostrar_atividade=False, lang=lang)}
{_paginacao(base, pagina, total, lang)}
<p class="nota" style="margin-top:20px">{t["at_outras"]} {outras}</p>"""
        titulo_pag = t["at_title"].format(a=desc, c=nome, t=n_fmt, emp=t["emp"][total != 1]) + (t["pagina_n"].format(p=pagina) if pagina > 1 else "")
        meta = t["at_meta"].format(t=n_fmt, a_min=desc[:1].lower() + desc[1:], c=nome)
        alt = {l: p_atividade(l, cidade, cod) + _qs(pagina) for l in IDIOMAS}
        return _pagina(titulo_pag, meta, base + _qs(pagina), corpo,
                       trilha=[(t["inicio"], "/"), (nome, p_cidade(lang, cidade)), (desc, None)],
                       indexar=total >= MIN_EMPRESAS_ATIVIDADE, lang=lang, alternativas=alt)
    return _em_cache(("ativ", lang, cidade, cod, pagina), gerar)


def _pagina_bairro(lang: str, cidade: str, bairro_slug: str, pagina: int):
    municipio, nome = _cidade_ou_404(cidade, lang)
    t = T[lang]
    achado = _agregados_cidade(municipio)["bairro_por_slug"].get(bairro_slug)
    if not achado:
        raise HTTPException(404, t["e404_bairro"].format(c=nome))
    bairro, total_b, variantes = achado
    marcas = ",".join("?" * len(variantes))
    base = p_bairro(lang, cidade, bairro_slug)

    def gerar():
        total, linhas = _listar(f"municipio = ? AND bairro IN ({marcas})", (municipio, *variantes), pagina)
        if linhas == [] and pagina > 1:
            raise HTTPException(404, t["e404_pag"])
        with dataset_queries._conn() as c:
            top = c.execute(f"SELECT cnae_principal, COUNT(*) n FROM empresas WHERE municipio = ? AND bairro IN ({marcas}) "
                            "GROUP BY 1 ORDER BY n DESC LIMIT 12", (municipio, *variantes)).fetchall()
        b = titulo(bairro)
        li_top = "".join(f'<li><a href="{p_atividade(lang, cidade, cod)}">{escape(cnae_desc(cod, lang) or cod)}</a> '
                         f'<span class="n">{_n(n, lang)}</span></li>' for cod, n in top if cod)
        n_fmt = _n(total, lang)
        corpo = f"""<h1>{escape(t["ba_h1"].format(b=b, c=nome))}</h1>
<p class="sub">{escape(t["ba_sub"].format(t=n_fmt))}</p>
<h2>{t["ba_h2_top"]}</h2><div class="card"><ul class="lista">{li_top}</ul></div>
<h2>{t["ba_h2_emp"]}</h2>{_tabela_empresas(linhas, mostrar_bairro=False, lang=lang)}
{_paginacao(base, pagina, total, lang)}"""
        titulo_pag = t["ba_title"].format(b=b, c=nome, t=n_fmt) + (t["pagina_n"].format(p=pagina) if pagina > 1 else "")
        alt = {l: p_bairro(l, cidade, bairro_slug) + _qs(pagina) for l in IDIOMAS}
        return _pagina(titulo_pag, t["ba_meta"].format(t=n_fmt, b=b, c=nome), base + _qs(pagina), corpo,
                       trilha=[(t["inicio"], "/"), (nome, p_cidade(lang, cidade)), (t["ba_trilha"].format(b=b), None)],
                       indexar=total_b >= MIN_EMPRESAS_BAIRRO, lang=lang, alternativas=alt)
    return _em_cache(("bairro", lang, cidade, bairro_slug, pagina), gerar)


def _fabrica_rotas(lang: str):
    def r_cidade(cidade: str):
        return _pagina_cidade(lang, cidade)

    def r_ativ(cidade: str, chave: str, pagina: int = Query(1, ge=1, le=2000)):
        return _pagina_atividade(lang, cidade, chave, pagina)

    def r_bairro(cidade: str, bairro_slug: str, pagina: int = Query(1, ge=1, le=2000)):
        return _pagina_bairro(lang, cidade, bairro_slug, pagina)
    return r_cidade, r_ativ, r_bairro


for _lang in IDIOMAS:
    _pre, _cid, _ativ, _bai = _ROTAS[_lang]
    _rc, _ra, _rb = _fabrica_rotas(_lang)
    router.add_api_route(f"{_pre}/{_cid}/{{cidade}}", _rc, methods=["GET"], include_in_schema=False)
    router.add_api_route(f"{_pre}/{_cid}/{{cidade}}/{_ativ}/{{chave}}", _ra, methods=["GET"], include_in_schema=False)
    router.add_api_route(f"{_pre}/{_cid}/{{cidade}}/{_bai}/{{bairro_slug}}", _rb, methods=["GET"], include_in_schema=False)


# ---------------------------------------------------------------- sitemaps

def _xml(conteudo: str) -> Response:
    return Response('<?xml version="1.0" encoding="UTF-8"?>' + conteudo, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# Empresas oferecidas no sitemap e a ordem (maiores primeiro). Ver docstring.
_FILTRO_SITEMAP = "COALESCE(regime_tributario, '') != 'MEI'"
_ORDEM_SITEMAP = ("CASE porte WHEN '05' THEN 0 WHEN '03' THEN 1 ELSE 2 END, "
                  "COALESCE(capital_social, 0) DESC, cnpj")


def _n_sitemaps_empresas() -> int:
    def gerar():
        with dataset_queries._conn() as c:
            n = c.execute(f"SELECT COUNT(*) FROM empresas WHERE {_FILTRO_SITEMAP}").fetchone()[0]
        return max(1, -(-n // URLS_POR_SITEMAP))
    return _em_cache(("n_sitemaps",), gerar)


def sitemap_indice() -> Response:
    lastmod = _data_banco()
    lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
    itens = [f"<sitemap><loc>{SITE_URL}/sitemaps/paginas.xml</loc>{lm}</sitemap>"]
    itens += [f"<sitemap><loc>{SITE_URL}/sitemaps/empresas-{i}.xml</loc>{lm}</sitemap>"
              for i in range(1, _n_sitemaps_empresas() + 1)]
    return _xml('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(itens) + "</sitemapindex>")


@router.get("/sitemaps/paginas.xml", include_in_schema=False)
def sitemap_paginas():
    """Páginas fixas + cidade/atividade/bairro nos 3 idiomas, cada uma com as
    alternativas hreflang (xhtml:link), como o Google recomenda."""
    def gerar():
        grupos = [{"pt": "/"}, {"pt": "/api"}, {"pt": "/docs"}]
        for slug, (municipio, _) in CIDADES.items():
            grupos.append({l: p_cidade(l, slug) for l in IDIOMAS})
            a = _agregados_cidade(municipio)
            grupos += [{l: p_atividade(l, slug, cod) for l in IDIOMAS}
                       for cod, n in a["atividades"] if n >= MIN_EMPRESAS_ATIVIDADE and dataset_queries.cnae_desc(cod)]
            grupos += [{l: p_bairro(l, slug, slugify(b)) for l in IDIOMAS}
                       for b, n in a["bairros"] if n >= MIN_EMPRESAS_BAIRRO]
        itens = []
        for g in grupos:
            alt = "" if len(g) == 1 else "".join(
                f'<xhtml:link rel="alternate" hreflang="{_HTML_LANG[l]}" href="{escape(SITE_URL + u)}"/>' for l, u in g.items())
            itens += [f"<url><loc>{escape(SITE_URL + u)}</loc>{alt}</url>" for u in g.values()]
        return ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                'xmlns:xhtml="http://www.w3.org/1999/xhtml">' + "".join(itens) + "</urlset>")
    return _xml(_em_cache(("sm_paginas",), gerar))


@router.get("/sitemaps/empresas-{n}.xml", include_in_schema=False)
def sitemap_empresas(n: int):
    if n < 1 or n > _n_sitemaps_empresas():
        raise HTTPException(404, "Sitemap inexistente.")

    def gerar():
        with dataset_queries._conn() as c:
            linhas = c.execute(f"SELECT cnpj, TRIM(razao_social), TRIM(nome_fantasia) FROM empresas "
                               f"WHERE {_FILTRO_SITEMAP} ORDER BY {_ORDEM_SITEMAP} LIMIT ? OFFSET ?",
                               (URLS_POR_SITEMAP, (n - 1) * URLS_POR_SITEMAP)).fetchall()
        removidos = _remocoes()
        corpo = "".join(f"<url><loc>{escape(SITE_URL + url_empresa(r[0], r[1], r[2]))}</loc></url>"
                        for r in linhas if r[0] not in removidos)
        return '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + corpo + "</urlset>"
    return _xml(_em_cache(("sm_emp", n), gerar))
