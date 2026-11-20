"""
Rotas de cadastro/login, conta do usuário, chaves de API e doação (Pix).

Login: Google (OAuth 2.0, fluxo de código) ou link mágico por e-mail. Não há
senha. A sessão é um cookie HttpOnly (`gv_sessao`, 30 dias, SameSite=Lax —
o que também barra POST/DELETE de outro site com o cookie).

O link do e-mail abre uma página com o botão "Entrar" (POST) em vez de logar
direto no GET: filtros de e-mail corporativo (Outlook Safe Links etc.) abrem
os links sozinhos e queimariam o link de uso único.
"""
import os
import re
import secrets
from html import escape

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

import config
from src import contas

router = APIRouter()

SITE_URL = (os.environ.get("SITE_URL") or "https://empresas.brunokobi.tech").rstrip("/")
_COOKIE_SEGURO = SITE_URL.startswith("https://")
_COOKIE_STATE = "gv_oauth_state"
_COOKIE_VOLTAR = "gv_voltar"


def _voltar_url(cnpj: str | None) -> str:
    # Fluxo OAuth do MCP: depois do login, volta para a tela de autorização.
    if (cnpj or "").startswith("/oauth/authorize?") and "//" not in cnpj and "\\" not in cnpj:
        return cnpj
    cnpj = re.sub(r"\D", "", cnpj or "")
    return f"/?empresa={cnpj}" if len(cnpj) == 14 else "/"


def _logar(resposta: Response, email: str, nome: str | None, provedor: str) -> Response:
    uid = contas.obter_ou_criar_usuario(email, nome, provedor)
    token = contas.criar_sessao(uid)
    resposta.set_cookie(contas.COOKIE_SESSAO, token, max_age=contas.SESSAO_DIAS * 86400,
                        httponly=True, secure=_COOKIE_SEGURO, samesite="lax", path="/")
    return resposta


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")) or "?"


def exigir_usuario(request: Request):
    if not contas.cadastro_ativo():
        return None  # cadastro ainda não configurado: recurso aberto
    u = contas.usuario_da_requisicao(request)
    if not u:
        raise HTTPException(status_code=401, detail={
            "erro": "login_necessario",
            "mensagem": f"Entre em {SITE_URL} (Google ou e-mail, grátis) para usar este recurso. "
                        "Pela API/MCP, envie a chave em 'Authorization: Bearer gv_...'."})
    return u


def _pagina(titulo: str, corpo: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(status_code=status, content=f"""<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{escape(titulo)}</title>
<style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#04060a;color:#e6edf3;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:16px}}
.card{{max-width:420px;width:100%;background:#0d1117;border:1px solid #21262d;border-radius:14px;padding:28px;text-align:center}}
h1{{font-size:20px;margin:0 0 10px}}p{{color:#9aa4ae;line-height:1.5}}
button,a.btn{{display:inline-block;margin-top:14px;background:#2ea043;color:#fff;border:0;border-radius:8px;
padding:11px 22px;font-size:15px;cursor:pointer;text-decoration:none}}</style></head>
<body><div class="card">{corpo}</div></body></html>""")


# ---------------------------------------------------------------- Google

@router.get("/auth/google", include_in_schema=False)
def auth_google(voltar: str = None):
    if not contas.metodos_login()["google"]:
        raise HTTPException(404, "Login com Google não configurado.")
    state = secrets.token_urlsafe(24)
    r = RedirectResponse(contas.url_google(state, f"{SITE_URL}/auth/google/callback"), status_code=302)
    r.set_cookie(_COOKIE_STATE, state, max_age=600, httponly=True, secure=_COOKIE_SEGURO, samesite="lax")
    r.set_cookie(_COOKIE_VOLTAR, _voltar_url(voltar), max_age=600, httponly=True, secure=_COOKIE_SEGURO, samesite="lax")
    return r


@router.get("/auth/google/callback", include_in_schema=False)
def auth_google_callback(request: Request, code: str = None, state: str = None):
    esperado = request.cookies.get(_COOKIE_STATE)
    if not code or not state or not esperado or not secrets.compare_digest(state, esperado):
        return _pagina("Falha no login", "<h1>Não foi possível entrar</h1><p>O pedido de login expirou "
                       "ou é inválido. Tente de novo.</p><a class='btn' href='/'>Voltar ao site</a>", 400)
    res = contas.usuario_google(code, f"{SITE_URL}/auth/google/callback")
    if not res:
        return _pagina("Falha no login", "<h1>Não foi possível entrar</h1><p>O Google não confirmou um "
                       "e-mail verificado para esta conta.</p><a class='btn' href='/'>Voltar ao site</a>", 400)
    voltar = request.cookies.get(_COOKIE_VOLTAR) or "/"
    r = RedirectResponse(voltar if voltar.startswith("/") and not voltar.startswith("//") else "/", status_code=302)
    r.delete_cookie(_COOKIE_STATE)
    r.delete_cookie(_COOKIE_VOLTAR)
    return _logar(r, res[0], res[1], "google")


# ---------------------------------------------------------------- e-mail

@router.post("/auth/email", include_in_schema=False)
async def auth_email(request: Request):
    if not contas.metodos_login()["email"]:
        raise HTTPException(404, "Login por e-mail não configurado.")
    try:
        dados = await request.json()
    except Exception:
        dados = {}
    email = contas.normalizar_email(dados.get("email"))
    if not email:
        raise HTTPException(400, "E-mail inválido.")
    try:
        token = contas.criar_link_email(email, _ip(request))
    except contas.LimiteEnvio:
        raise HTTPException(429, "Muitos pedidos de link. Aguarde uma hora e tente de novo.")
    voltar = re.sub(r"\D", "", str(dados.get("voltar") or ""))
    link = f"{SITE_URL}/auth/email/entrar?token={token}" + (f"&voltar={voltar}" if len(voltar) == 14 else "")
    html = (f"<p>Olá!</p><p>Para entrar no <b>Empresas · Grande Vitória</b>, clique no link abaixo "
            f"(vale por {contas.LINK_MINUTOS} minutos e só uma vez):</p>"
            f"<p><a href=\"{link}\">Entrar no site</a></p>"
            f"<p style=\"color:#666;font-size:12px\">Se você não pediu este acesso, ignore este e-mail.</p>")
    texto = (f"Para entrar no Empresas · Grande Vitória, abra o link (vale por {contas.LINK_MINUTOS} minutos "
             f"e só uma vez):\n{link}\n\nSe você não pediu este acesso, ignore este e-mail.")
    try:
        contas.enviar_email(email, "Seu link de acesso — Empresas · Grande Vitória", html, texto)
    except Exception:
        raise HTTPException(503, "Não foi possível enviar o e-mail agora. Tente de novo em alguns minutos ou entre com o Google.")
    return {"ok": True, "mensagem": f"Enviamos um link de acesso para {email}. Confira também o spam."}


@router.get("/auth/email/entrar", include_in_schema=False)
def auth_email_pagina(token: str = "", voltar: str = ""):
    return _pagina("Entrar", f"""<h1>Entrar no Empresas · Grande Vitória</h1>
<p>Clique no botão para concluir o login.</p>
<form method="post" action="/auth/email/entrar">
<input type="hidden" name="token" value="{escape(token)}"><input type="hidden" name="voltar" value="{escape(voltar)}">
<button type="submit">Entrar</button></form>""")


@router.post("/auth/email/entrar", include_in_schema=False)
def auth_email_entrar(token: str = Form(""), voltar: str = Form("")):
    email = contas.usar_link_email(token)
    if not email:
        return _pagina("Link inválido", "<h1>Link expirado ou já usado</h1><p>Peça um novo link no site.</p>"
                       "<a class='btn' href='/'>Voltar ao site</a>", 400)
    return _logar(RedirectResponse(_voltar_url(voltar), status_code=303), email, None, "email")


@router.post("/auth/sair", include_in_schema=False)
def auth_sair(request: Request):
    contas.encerrar_sessao(request.cookies.get(contas.COOKIE_SESSAO))
    r = JSONResponse({"ok": True})
    r.delete_cookie(contas.COOKIE_SESSAO, path="/")
    return r


# ---------------------------------------------------------------- conta

@router.get("/conta", summary="Conta do usuário logado: cota do mês e chaves de API", tags=["Conta"])
def get_conta(request: Request):
    u = contas.usuario_da_requisicao(request)
    base = {"metodos_login": contas.metodos_login(), "cota_gratis": contas.COTA_MENSAL,
            "cadastro_ativo": contas.cadastro_ativo()}
    if not u:
        return {"logado": False, **base}
    from src import oauth_mcp
    return {"logado": True, **base, "email": u["email"], "nome": u["nome"],
            "uso": contas.uso_do_mes(u), "chaves": contas.listar_chaves(u["id"]),
            "aplicativos": oauth_mcp.aplicativos_conectados(u["id"])}


@router.delete("/conta/aplicativos/{client_id}", summary="Revoga o acesso de um aplicativo MCP conectado por OAuth", tags=["Conta"])
def delete_aplicativo(client_id: str, request: Request):
    from src import oauth_mcp
    u = exigir_usuario(request)
    if not u or not oauth_mcp.revogar_aplicativo(u["id"], client_id):
        raise HTTPException(404, "Aplicativo não encontrado.")
    return {"ok": True}


@router.post("/conta/chaves", summary="Cria uma chave de API (mostrada uma única vez)", tags=["Conta"])
async def post_chave(request: Request):
    u = exigir_usuario(request)
    if not u or not contas.usuario_da_sessao(request.cookies.get(contas.COOKIE_SESSAO)):
        raise HTTPException(403, "Chaves só podem ser criadas pelo site, logado.")
    try:
        dados = await request.json()
    except Exception:
        dados = {}
    try:
        chave = contas.criar_chave(u["id"], dados.get("nome"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"chave": chave, "aviso": "Guarde a chave agora: ela não é mostrada de novo."}


@router.delete("/conta/chaves/{prefixo}", summary="Revoga uma chave de API", tags=["Conta"])
def delete_chave(prefixo: str, request: Request):
    u = exigir_usuario(request)
    if not u or not contas.revogar_chave(u["id"], prefixo):
        raise HTTPException(404, "Chave não encontrada.")
    return {"ok": True}


@router.delete("/conta", summary="Exclui a conta e todos os dados dela", tags=["Conta"])
def delete_conta(request: Request):
    u = exigir_usuario(request)
    if not u or not contas.usuario_da_sessao(request.cookies.get(contas.COOKIE_SESSAO)):
        raise HTTPException(403, "A conta só pode ser excluída pelo site, logado.")
    from src import oauth_mcp
    oauth_mcp.excluir_do_usuario(u["id"])
    contas.excluir_usuario(u["id"])
    r = JSONResponse({"ok": True})
    r.delete_cookie(contas.COOKIE_SESSAO, path="/")
    return r


# ---------------------------------------------------------------- doação

_PIX_SVG = None


@router.get("/doacao", summary="Formas de apoiar o projeto (Pix e GitHub Sponsors)", tags=["Doação"])
def get_doacao():
    return {"pix": {"chave": config.PIX_CHAVE, "tipo": "celular",
                    "copia_e_cola": contas.pix_copia_e_cola(config.PIX_CHAVE, config.PIX_NOME, config.PIX_CIDADE),
                    "qrcode_svg": "/doacao/pix.svg"},
            "github_sponsors": config.GITHUB_SPONSORS_URL}


@router.get("/doacao/pix.svg", include_in_schema=False)
def get_pix_svg():
    global _PIX_SVG
    if _PIX_SVG is None:
        import io
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(contas.pix_copia_e_cola(config.PIX_CHAVE, config.PIX_NOME, config.PIX_CIDADE),
                          image_factory=qrcode.image.svg.SvgPathFillImage, box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf)
        _PIX_SVG = buf.getvalue()
    return Response(_PIX_SVG, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})
