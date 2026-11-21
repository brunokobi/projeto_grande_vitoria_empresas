"""
OAuth 2.1 para o MCP remoto com login (`/mcp-conta/`).

Por quê um segundo endereço: clientes como os conectores do claude.ai só
iniciam o login OAuth quando o servidor responde 401 ao acesso anônimo. O
`/mcp/` continua aberto (ferramentas livres sem conta; relatório com chave),
e o `/mcp-conta/` exige token: sem ele responde 401 com o cabeçalho
`WWW-Authenticate` apontando para os metadados (RFC 9728), e o cliente faz o
fluxo sozinho:

1. `GET /.well-known/oauth-protected-resource/mcp-conta/` → servidor de autorização;
2. `GET /.well-known/oauth-authorization-server` → endpoints (RFC 8414);
3. `POST /oauth/register` → registro dinâmico do cliente (RFC 7591);
4. `GET /oauth/authorize` → login no site (Google/e-mail) + tela "Autorizar";
5. `POST /oauth/token` → troca do código com PKCE S256 (obrigatório) e
   renovação por refresh token (rotativo).

O token de acesso (`gvat_...`) identifica a conta como uma chave de API: o
relatório (`obter_empresa`) gasta a mesma cota mensal. Tokens e códigos ficam
só como hash em `data/contas.db`. "Minha conta" lista os aplicativos
conectados e permite revogar.
"""
import base64
import hashlib
import json
import re
import secrets
import time
from html import escape
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from src import contas
from src.contas_rotas import SITE_URL, _pagina

router = APIRouter()

# "G" oficial do Google (botão de login, conforme as regras de marca).
_G_LOGO = '<svg style="width:18px;height:18px" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>'

CAMINHO_MCP = "/mcp-conta/"
RECURSO = SITE_URL + CAMINHO_MCP
METADADOS_RECURSO = SITE_URL + "/.well-known/oauth-protected-resource" + CAMINHO_MCP.rstrip("/")
ACESSO_SEG = 24 * 3600
RENOVACAO_SEG = 90 * 86400
CODIGO_SEG = 300
MAX_CLIENTES_POR_HORA = 30


def _agora() -> int:
    return int(time.time())


def _criar_tabelas():
    with contas._conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS oauth_clientes (
            client_id TEXT PRIMARY KEY, nome TEXT, redirect_uris TEXT NOT NULL, criado_em INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS oauth_codigos (
            codigo_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, usuario_id INTEGER NOT NULL,
            redirect_uri TEXT NOT NULL, desafio TEXT NOT NULL, expira_em INTEGER NOT NULL, usado INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            token_hash TEXT PRIMARY KEY, tipo TEXT NOT NULL, client_id TEXT NOT NULL, usuario_id INTEGER NOT NULL,
            criado_em INTEGER NOT NULL, expira_em INTEGER NOT NULL, revogado INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS ix_oauth_tokens_usuario ON oauth_tokens(usuario_id);
        """)


_tabelas_ok = False


def _db():
    global _tabelas_ok
    if not _tabelas_ok:
        _criar_tabelas()
        _tabelas_ok = True
    return contas._conn()


def _uri_valida(uri: str) -> bool:
    try:
        u = urlparse(uri)
    except ValueError:
        return False
    if u.fragment or not u.netloc:
        return False
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1"))


# ---------------------------------------------------------------- tokens (usados por contas.usuario_da_requisicao)

def usuario_do_token(token: str):
    if not token or not token.startswith("gvat_"):
        return None
    with _db() as c:
        row = c.execute("SELECT usuario_id FROM oauth_tokens WHERE token_hash = ? AND tipo = 'acesso' "
                        "AND revogado = 0 AND expira_em > ?", (contas._hash(token), _agora())).fetchone()
        return contas._usuario(c, row["usuario_id"]) if row else None


def _emitir(c, client_id: str, usuario_id: int) -> dict:
    acesso, renovacao = "gvat_" + secrets.token_urlsafe(32), "gvrt_" + secrets.token_urlsafe(32)
    agora = _agora()
    c.execute("INSERT INTO oauth_tokens VALUES (?,?,?,?,?,?,0)",
              (contas._hash(acesso), "acesso", client_id, usuario_id, agora, agora + ACESSO_SEG))
    c.execute("INSERT INTO oauth_tokens VALUES (?,?,?,?,?,?,0)",
              (contas._hash(renovacao), "renovacao", client_id, usuario_id, agora, agora + RENOVACAO_SEG))
    return {"access_token": acesso, "token_type": "Bearer", "expires_in": ACESSO_SEG,
            "refresh_token": renovacao, "scope": "relatorios"}


def aplicativos_conectados(usuario_id: int) -> list:
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT t.client_id, COALESCE(k.nome, 'Aplicativo MCP') nome, MIN(t.criado_em) desde, MAX(t.criado_em) ultimo "
            "FROM oauth_tokens t LEFT JOIN oauth_clientes k ON k.client_id = t.client_id "
            "WHERE t.usuario_id = ? AND t.revogado = 0 AND t.tipo = 'renovacao' AND t.expira_em > ? "
            "GROUP BY t.client_id ORDER BY ultimo DESC", (usuario_id, _agora()))]


def revogar_aplicativo(usuario_id: int, client_id: str) -> bool:
    with _db() as c:
        return c.execute("UPDATE oauth_tokens SET revogado = 1 WHERE usuario_id = ? AND client_id = ? AND revogado = 0",
                         (usuario_id, client_id)).rowcount > 0


def excluir_do_usuario(usuario_id: int):
    with _db() as c:
        c.execute("DELETE FROM oauth_tokens WHERE usuario_id = ?", (usuario_id,))
        c.execute("DELETE FROM oauth_codigos WHERE usuario_id = ?", (usuario_id,))


# ---------------------------------------------------------------- metadados

@router.get("/.well-known/oauth-protected-resource" + CAMINHO_MCP.rstrip("/"), include_in_schema=False)
@router.get("/.well-known/oauth-protected-resource" + CAMINHO_MCP, include_in_schema=False)
@router.get("/.well-known/oauth-protected-resource", include_in_schema=False)
def metadados_recurso():
    return {"resource": RECURSO, "authorization_servers": [SITE_URL], "scopes_supported": ["relatorios"],
            "bearer_methods_supported": ["header"], "resource_name": "Empresas da Grande Vitória (MCP com conta)"}


@router.get("/.well-known/oauth-authorization-server", include_in_schema=False)
def metadados_servidor():
    return {"issuer": SITE_URL,
            "authorization_endpoint": f"{SITE_URL}/oauth/authorize",
            "token_endpoint": f"{SITE_URL}/oauth/token",
            "registration_endpoint": f"{SITE_URL}/oauth/register",
            "revocation_endpoint": f"{SITE_URL}/oauth/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": ["relatorios"],
            "service_documentation": f"{SITE_URL}/docs"}


# ---------------------------------------------------------------- registro dinâmico

@router.post("/oauth/register", include_in_schema=False)
async def registrar(request: Request):
    try:
        d = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_client_metadata"}, status_code=400)
    uris = d.get("redirect_uris") or []
    if not isinstance(uris, list) or not uris or len(uris) > 10 or not all(isinstance(u, str) and _uri_valida(u) for u in uris):
        return JSONResponse({"error": "invalid_redirect_uri",
                             "error_description": "redirect_uris precisa ser https (ou http://localhost)"}, status_code=400)
    agora = _agora()
    with _db() as c:
        if c.execute("SELECT COUNT(*) FROM oauth_clientes WHERE criado_em > ?", (agora - 3600,)).fetchone()[0] >= MAX_CLIENTES_POR_HORA * 10:
            return JSONResponse({"error": "temporarily_unavailable"}, status_code=429)
        client_id = "gvc_" + secrets.token_urlsafe(18)
        nome = str(d.get("client_name") or "")[:80] or None
        c.execute("INSERT INTO oauth_clientes VALUES (?,?,?,?)", (client_id, nome, json.dumps(uris), agora))
    return JSONResponse({"client_id": client_id, "client_id_issued_at": agora, "redirect_uris": uris,
                         "client_name": nome, "grant_types": ["authorization_code", "refresh_token"],
                         "response_types": ["code"], "token_endpoint_auth_method": "none"}, status_code=201)


def _cliente(client_id: str):
    with _db() as c:
        r = c.execute("SELECT client_id, nome, redirect_uris FROM oauth_clientes WHERE client_id = ?",
                      (client_id or "",)).fetchone()
    return {"client_id": r["client_id"], "nome": r["nome"], "uris": json.loads(r["redirect_uris"])} if r else None


# ---------------------------------------------------------------- autorização

def _erro_redirect(redirect_uri: str, erro: str, state: str | None):
    q = {"error": erro, **({"state": state} if state else {})}
    return RedirectResponse(redirect_uri + ("&" if "?" in redirect_uri else "?") + urlencode(q), status_code=302)


@router.get("/oauth/authorize", include_in_schema=False)
def autorizar(request: Request, client_id: str = "", redirect_uri: str = "", response_type: str = "",
              code_challenge: str = "", code_challenge_method: str = "", state: str = None, scope: str = None,
              resource: str = None):
    cli = _cliente(client_id)
    if not cli or redirect_uri not in cli["uris"]:
        # Sem cliente/URI válidos não se redireciona (evita redirecionamento aberto).
        return _pagina("Pedido inválido", "<h1>Pedido de autorização inválido</h1><p>O aplicativo não está "
                       "registrado ou o endereço de retorno não confere.</p>", 400)
    if response_type != "code":
        return _erro_redirect(redirect_uri, "unsupported_response_type", state)
    if code_challenge_method != "S256" or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", code_challenge or ""):
        return _erro_redirect(redirect_uri, "invalid_request", state)
    if not contas.cadastro_ativo():
        return _pagina("Indisponível", "<h1>Login ainda não disponível</h1><p>O cadastro do site ainda não foi ativado.</p>", 503)

    usuario = contas.usuario_da_sessao(request.cookies.get(contas.COOKIE_SESSAO))
    volta = str(request.url.path) + "?" + str(request.url.query)
    if not usuario:
        m = contas.metodos_login()
        botoes = ""
        if m["google"]:
            botoes += (f'<a class="btn" style="background:#fff;color:#1f1f1f;border:1px solid #dadce0;display:inline-flex;'
                       f'align-items:center;gap:10px" href="/auth/google?{urlencode({"voltar": volta})}">'
                       + _G_LOGO + 'Entrar com Google</a><br>')
        if m["email"]:
            botoes += ('<p>ou receba um link no e-mail:</p><form method="post" action="/oauth/link-email">'
                       f'<input type="hidden" name="voltar" value="{escape(volta)}">'
                       '<input type="email" name="email" required placeholder="seu@email.com" '
                       'style="padding:10px;border-radius:8px;border:1px solid #21262d;background:#04060a;color:#e6edf3;width:100%">'
                       '<button type="submit">Enviar link</button></form>')
        return _pagina("Entrar", f"<h1>Entrar para conectar</h1><p><b>{escape(cli['nome'] or 'Um aplicativo MCP')}</b> "
                       f"quer usar sua conta do Empresas · Grande Vitória.</p>{botoes}")

    campos = "".join(f'<input type="hidden" name="{k}" value="{escape(v)}">' for k, v in {
        "client_id": client_id, "redirect_uri": redirect_uri, "code_challenge": code_challenge,
        "state": state or ""}.items())
    host = escape(urlparse(redirect_uri).hostname or "")
    return _pagina("Autorizar", f"""<h1>Autorizar acesso</h1>
<p><b>{escape(cli['nome'] or 'Um aplicativo MCP')}</b> ({host}) quer usar sua conta
<b>{escape(usuario['email'])}</b> para abrir relatórios de empresas pelo MCP.</p>
<p>Cada relatório aberto por ele gasta 1 da sua cota mensal ({contas.cota_do_usuario(usuario)}).
Você pode revogar o acesso em "Minha conta".</p>
<form method="post" action="/oauth/authorize">{campos}
<button type="submit" name="decisao" value="permitir">Autorizar</button>
<button type="submit" name="decisao" value="negar" style="background:#30363d">Cancelar</button></form>""")


@router.post("/oauth/authorize", include_in_schema=False)
def autorizar_decisao(request: Request, client_id: str = Form(""), redirect_uri: str = Form(""),
                      code_challenge: str = Form(""), state: str = Form(""), decisao: str = Form("")):
    cli = _cliente(client_id)
    if not cli or redirect_uri not in cli["uris"]:
        return _pagina("Pedido inválido", "<h1>Pedido de autorização inválido</h1>", 400)
    usuario = contas.usuario_da_sessao(request.cookies.get(contas.COOKIE_SESSAO))
    if not usuario:
        return _pagina("Sessão expirada", "<h1>Sessão expirada</h1><p>Volte ao aplicativo e tente conectar de novo.</p>", 401)
    if decisao != "permitir":
        return _erro_redirect(redirect_uri, "access_denied", state or None)
    codigo = secrets.token_urlsafe(32)
    with _db() as c:
        c.execute("INSERT INTO oauth_codigos VALUES (?,?,?,?,?,?,0)",
                  (contas._hash(codigo), client_id, usuario["id"], redirect_uri, code_challenge, _agora() + CODIGO_SEG))
    q = {"code": codigo, **({"state": state} if state else {})}
    return RedirectResponse(redirect_uri + ("&" if "?" in redirect_uri else "?") + urlencode(q), status_code=302)


@router.post("/oauth/link-email", include_in_schema=False)
def oauth_link_email(request: Request, email: str = Form(""), voltar: str = Form("")):
    """Login por e-mail durante o fluxo OAuth: o link volta para a tela de autorização."""
    from src import contas_rotas
    e = contas.normalizar_email(email)
    if not e or not voltar.startswith("/oauth/authorize?"):
        return _pagina("E-mail inválido", "<h1>E-mail inválido</h1>", 400)
    try:
        token = contas.criar_link_email(e, contas_rotas._ip(request))
    except contas.LimiteEnvio:
        return _pagina("Aguarde", "<h1>Muitos pedidos</h1><p>Aguarde uma hora e tente de novo.</p>", 429)
    link = f"{SITE_URL}/auth/email/entrar?{urlencode({'token': token, 'voltar': voltar})}"
    try:
        contas.enviar_email(e, "Seu link de acesso — Empresas · Grande Vitória",
                            f'<p>Para concluir a conexão do aplicativo, <a href="{link}">clique aqui</a> '
                            f"(vale por {contas.LINK_MINUTOS} minutos, uma vez).</p>",
                            f"Para concluir a conexão do aplicativo, abra: {link}")
    except Exception:
        return _pagina("Erro", "<h1>Não foi possível enviar o e-mail agora</h1>", 503)
    return _pagina("Confira o e-mail", f"<h1>Confira seu e-mail</h1><p>Enviamos um link para {escape(e)}. "
                   "Abra o link neste mesmo navegador.</p>")


# ---------------------------------------------------------------- token

def _pkce_ok(verificador: str, desafio: str) -> bool:
    if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verificador or ""):
        return False
    calc = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return secrets.compare_digest(calc, desafio)


def _erro_token(erro: str, status: int = 400):
    return JSONResponse({"error": erro}, status_code=status, headers={"Cache-Control": "no-store"})


@router.post("/oauth/token", include_in_schema=False)
async def token(request: Request):
    form = await request.form()
    grant = form.get("grant_type")
    client_id = form.get("client_id") or ""
    if not _cliente(client_id):
        return _erro_token("invalid_client", 401)
    with _db() as c:
        if grant == "authorization_code":
            row = c.execute("SELECT * FROM oauth_codigos WHERE codigo_hash = ?",
                            (contas._hash(form.get("code") or ""),)).fetchone()
            if (not row or row["usado"] or row["expira_em"] < _agora() or row["client_id"] != client_id
                    or row["redirect_uri"] != form.get("redirect_uri")):
                return _erro_token("invalid_grant")
            c.execute("UPDATE oauth_codigos SET usado = 1 WHERE codigo_hash = ?", (row["codigo_hash"],))
            if not _pkce_ok(form.get("code_verifier") or "", row["desafio"]):
                return _erro_token("invalid_grant")
            corpo = _emitir(c, client_id, row["usuario_id"])
        elif grant == "refresh_token":
            h = contas._hash(form.get("refresh_token") or "")
            row = c.execute("SELECT * FROM oauth_tokens WHERE token_hash = ? AND tipo = 'renovacao'", (h,)).fetchone()
            if not row or row["revogado"] or row["expira_em"] < _agora() or row["client_id"] != client_id:
                return _erro_token("invalid_grant")
            c.execute("UPDATE oauth_tokens SET revogado = 1 WHERE token_hash = ?", (h,))  # rotação
            corpo = _emitir(c, client_id, row["usuario_id"])
        else:
            return _erro_token("unsupported_grant_type")
    return JSONResponse(corpo, headers={"Cache-Control": "no-store"})


@router.post("/oauth/revoke", include_in_schema=False)
async def revogar(request: Request):
    form = await request.form()
    with _db() as c:
        c.execute("UPDATE oauth_tokens SET revogado = 1 WHERE token_hash = ?", (contas._hash(form.get("token") or ""),))
    return JSONResponse({}, status_code=200)


# ---------------------------------------------------------------- proteção do /mcp-conta/

class ExigirToken:
    """ASGI: deixa passar só com token OAuth válido (ou chave gv_ da conta);
    senão 401 com WWW-Authenticate → o cliente MCP inicia o login."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
        tok = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        ok = usuario_do_token(tok) if tok.startswith("gvat_") else contas.usuario_da_chave(tok)
        if not ok:
            corpo = json.dumps({"error": "invalid_token", "error_description": "Login necessário"}).encode()
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(corpo)).encode()),
                (b"www-authenticate", f'Bearer error="invalid_token", resource_metadata="{METADADOS_RECURSO}"'.encode())]})
            await send({"type": "http.response.body", "body": corpo})
            return
        await self.app(scope, receive, send)
