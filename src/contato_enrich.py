"""
Enriquecimento de contato e redes sociais — etapa `contato`. 100% grátis,
sem API paga, sem cartão.

Para cada empresa da base:
  1. WhatsApp: deriva um link wa.me do telefone já cadastrado (só para
     números que parecem celular — DDD + 9 dígitos começando em 9). É um
     palpite (não confirma que o número tem WhatsApp), mas com boa taxa de
     acerto no varejo/PME.
  2. Site: infere do domínio do e-mail corporativo (ex.: contato@empresa.com.br
     -> https://empresa.com.br). Ignora provedores genéricos (gmail, etc.).
  3. Redes sociais: baixa o HTML do site da PRÓPRIA empresa e extrai os links
     de Instagram/Facebook/LinkedIn (normalmente no rodapé). Isso é legítimo
     — é o site público da empresa, não a plataforma social. NÃO fazemos
     scraping das redes sociais diretamente (violaria os ToS e é bloqueado).

Rate limit: só há requisição de rede para empresas com site inferido; entre
esses fetches há uma pausa educada. É retomável via checkpoint (se cair,
rode de novo e continua de onde parou).
"""
import re
import time

import requests

import config
from src import db_utils, checkpoint

CHECKPOINT_NAME = "contato_processados"

_RE_INSTAGRAM = re.compile(r'https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]{2,}', re.I)
_RE_FACEBOOK = re.compile(r'https?://(?:www\.)?(?:facebook|fb)\.com/[A-Za-z0-9_.\-/]{2,}', re.I)
_RE_LINKEDIN = re.compile(r'https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9_.\-%]{2,}', re.I)

# Caminhos que não são perfil de empresa (widgets, compartilhamento, posts,
# namespaces de HTML como facebook.com/2008/fbml).
_IGNORAR = ("/sharer", "/plugins", "/tr", "/dialog", "/p/", "/explore",
            "/accounts", "/reel", "/events", "/hashtag", "/2008", "fbml",
            "/login", "/policies", "/help", "/pages/", "/groups/")


def _whatsapp_de_telefone(telefone: str):
    if not telefone:
        return None
    d = "".join(c for c in telefone if c.isdigit())
    # Celular BR: 2 (DDD) + 9 dígitos começando em 9 = 11 dígitos.
    if len(d) == 11 and d[2] == "9":
        return f"https://wa.me/55{d}"
    return None


def _site_de_email(email: str):
    if not email or "@" not in email:
        return None
    dominio = email.split("@")[-1].strip().strip(" .;,<>\"'").lower()
    if not dominio or "." not in dominio:
        return None
    if dominio in config.EMAIL_DOMINIOS_GENERICOS:
        return None
    if not re.match(r"^[a-z0-9][a-z0-9.\-]+\.[a-z]{2,}(\.[a-z]{2,})?$", dominio):
        return None
    return f"https://{dominio}"


def _primeiro_link(regex, html: str):
    for m in regex.finditer(html):
        url = m.group(0).rstrip("\"'<>).,\\")
        if not any(t in url.lower() for t in _IGNORAR):
            return url
    return None


def _extrair_redes(html: str) -> dict:
    return {
        "instagram": _primeiro_link(_RE_INSTAGRAM, html),
        "facebook": _primeiro_link(_RE_FACEBOOK, html),
        "linkedin": _primeiro_link(_RE_LINKEDIN, html),
    }


def _buscar_redes_no_site(site: str) -> dict:
    """Tenta o domínio e o www; devolve as redes encontradas no HTML."""
    vazio = {"instagram": None, "facebook": None, "linkedin": None}
    candidatos = [site]
    if "://" in site and "://www." not in site:
        candidatos.append(site.replace("://", "://www.", 1))
    headers = {"User-Agent": config.CONTATO_USER_AGENT}
    for url in candidatos:
        try:
            resp = requests.get(url, timeout=config.CONTATO_HTTP_TIMEOUT,
                                headers=headers, allow_redirects=True)
            if resp.status_code == 200 and resp.text:
                redes = _extrair_redes(resp.text)
                if any(redes.values()):
                    return redes
        except requests.RequestException:
            continue
    return vazio


def _gravar(conn, cnpj, whatsapp, site, redes):
    conn.execute(
        """INSERT INTO enriquecimento_contato
           (cnpj_empresa, whatsapp, site, instagram, facebook, linkedin, data_enriquecimento)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(cnpj_empresa) DO UPDATE SET
             whatsapp=excluded.whatsapp, site=excluded.site,
             instagram=excluded.instagram, facebook=excluded.facebook,
             linkedin=excluded.linkedin, data_enriquecimento=excluded.data_enriquecimento
        """,
        (cnpj, whatsapp, site, redes["instagram"], redes["facebook"],
         redes["linkedin"], time.strftime("%Y-%m-%d %H:%M:%S")),
    )


def executar(limite_cnpjs: int = None):
    with db_utils.get_conn() as conn:
        empresas = conn.execute(
            "SELECT cnpj, telefone, email FROM empresas"
        ).fetchall()

    processados = checkpoint.carregar(CHECKPOINT_NAME)
    pendentes = [e for e in empresas if e["cnpj"] not in processados]
    if limite_cnpjs:
        pendentes = pendentes[:limite_cnpjs]

    com_site = sum(1 for e in pendentes if _site_de_email(e["email"]))
    print(f"[contato_enrich] {len(pendentes)} empresas pendentes; ~{com_site} "
          f"com site inferido para buscar redes (~{com_site * config.CONTATO_RATE_LIMIT_SLEEP_SECONDS / 3600:.1f}h).")

    # Checkpoint em lote (a cada 200) — evita reescrever o JSON a cada empresa.
    processados = set(processados)
    achou_wpp = achou_site = achou_rede = 0

    with db_utils.get_conn() as conn:
        for i, emp in enumerate(pendentes):
            whatsapp = _whatsapp_de_telefone(emp["telefone"])
            site = _site_de_email(emp["email"])
            redes = {"instagram": None, "facebook": None, "linkedin": None}
            if site:
                redes = _buscar_redes_no_site(site)
                time.sleep(config.CONTATO_RATE_LIMIT_SLEEP_SECONDS)

            if whatsapp or site or any(redes.values()):
                _gravar(conn, emp["cnpj"], whatsapp, site, redes)
                achou_wpp += bool(whatsapp)
                achou_site += bool(site)
                achou_rede += bool(any(redes.values()))

            processados.add(emp["cnpj"])
            if (i + 1) % 200 == 0:
                conn.commit()
                checkpoint.salvar(CHECKPOINT_NAME, processados)
                print(f"[contato_enrich] {i+1}/{len(pendentes)} | "
                      f"whatsapp={achou_wpp} site={achou_site} redes={achou_rede}")

        conn.commit()
    checkpoint.salvar(CHECKPOINT_NAME, processados)
    print(f"[contato_enrich] Concluído: {achou_wpp} WhatsApp, {achou_site} sites, "
          f"{achou_rede} com rede social.")


if __name__ == "__main__":
    executar()
