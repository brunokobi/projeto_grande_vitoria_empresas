"""
Contas de usuário: cadastro (Google ou link por e-mail), sessões, chaves de
API (MCP/REST) e cota mensal de relatórios.

"Relatório" = a visão 360º de uma empresa (`GET /empresas/{cnpj}` ou a
ferramenta MCP `obter_empresa` pelo servidor remoto). Rever o mesmo CNPJ no
mesmo mês não gasta cota de novo. O mês é o do horário de Brasília.

Banco próprio (`data/contas.db`, ou `CONTAS_DB`): o banco do dataset é
trocado inteiro a cada 2h pelo `refresh_dataset.py`, então os usuários não
podem morar nele. Tokens de sessão, chaves e links são guardados só como hash
SHA-256 — o valor em claro aparece uma única vez (cookie, tela ou e-mail).

Variáveis de ambiente (todas opcionais; sem elas o método some da tela):
- GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET — "Entrar com Google";
- EMAIL_PROVIDER (brevo|resend), EMAIL_API_KEY, EMAIL_FROM — link por e-mail;
- COTA_MENSAL (padrão 10), CONTAS_DB.
"""
import hashlib
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

import config

DB_PATH = Path(os.environ.get("CONTAS_DB") or config.BASE_DIR / "data" / "contas.db")
COTA_MENSAL = int(os.environ.get("COTA_MENSAL") or 10)
SESSAO_DIAS = 30
LINK_MINUTOS = 20
MAX_CHAVES = 5
# Limite de envio de link por e-mail (anti-abuso): por endereço e por IP, por hora.
ENVIOS_POR_EMAIL_HORA = 3
ENVIOS_POR_IP_HORA = 10

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or None
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or None
EMAIL_PROVIDER = (os.environ.get("EMAIL_PROVIDER") or "").strip().lower() or None
EMAIL_API_KEY = os.environ.get("EMAIL_API_KEY") or None
EMAIL_FROM = os.environ.get("EMAIL_FROM") or None

COOKIE_SESSAO = "gv_sessao"
_TZ = ZoneInfo("America/Sao_Paulo")
_RX_EMAIL = re.compile(r"^[^@\s]{1,64}@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
_lock = threading.RLock()
_iniciado = False


class LimiteEnvio(Exception):
    """Muitos pedidos de link por e-mail em pouco tempo."""


# ---------------------------------------------------------------- banco

def _conn():
    global _iniciado
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    if not _iniciado:
        with _lock:
            if not _iniciado:
                _criar_tabelas(c)
                _iniciado = True
    return c


def _criar_tabelas(c):
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        nome TEXT,
        provedor TEXT,
        cota_mensal INTEGER,          -- NULL = cota padrão (COTA_MENSAL)
        criado_em INTEGER NOT NULL,
        ultimo_login INTEGER
    );
    CREATE TABLE IF NOT EXISTS sessoes (
        token_hash TEXT PRIMARY KEY,
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        criado_em INTEGER NOT NULL,
        expira_em INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS chaves_api (
        chave_hash TEXT PRIMARY KEY,
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        prefixo TEXT NOT NULL,
        nome TEXT,
        criado_em INTEGER NOT NULL,
        ultimo_uso INTEGER,
        revogada INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS consumo (
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        mes TEXT NOT NULL,
        cnpj TEXT NOT NULL,
        origem TEXT,
        criado_em INTEGER NOT NULL,
        PRIMARY KEY (usuario_id, mes, cnpj)
    );
    CREATE TABLE IF NOT EXISTS links_email (
        token_hash TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        expira_em INTEGER NOT NULL,
        usado INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS envios_email (
        email TEXT NOT NULL,
        ip TEXT,
        em INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_envios_em ON envios_email(em);
    CREATE INDEX IF NOT EXISTS ix_sessoes_usuario ON sessoes(usuario_id);
    CREATE INDEX IF NOT EXISTS ix_chaves_usuario ON chaves_api(usuario_id);
    """)
    c.commit()


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def _agora() -> int:
    return int(time.time())


def mes_atual() -> str:
    return datetime.now(_TZ).strftime("%Y-%m")


def normalizar_email(email: str):
    e = (email or "").strip().lower()
    if len(e) > 254 or not _RX_EMAIL.match(e):
        return None
    return e


def metodos_login() -> dict:
    return {
        "google": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        "email": bool(EMAIL_PROVIDER in ("brevo", "resend") and EMAIL_API_KEY and EMAIL_FROM),
    }


def cadastro_ativo() -> bool:
    """Login e cota só valem com pelo menos um método configurado. Sem
    nenhum, o site funciona aberto como antes (deploy seguro antes de as
    credenciais do Google/e-mail existirem)."""
    m = metodos_login()
    return m["google"] or m["email"]


# ---------------------------------------------------------------- usuários e sessões

def obter_ou_criar_usuario(email: str, nome: str = None, provedor: str = None) -> int:
    agora = _agora()
    with _conn() as c:
        row = c.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
        if row:
            c.execute("UPDATE usuarios SET ultimo_login = ?, nome = COALESCE(nome, ?) WHERE id = ?",
                      (agora, nome, row["id"]))
            return row["id"]
        cur = c.execute("INSERT INTO usuarios (email, nome, provedor, criado_em, ultimo_login) "
                        "VALUES (?,?,?,?,?)", (email, nome, provedor, agora, agora))
        return cur.lastrowid


def criar_sessao(usuario_id: int) -> str:
    token = secrets.token_urlsafe(32)
    agora = _agora()
    with _conn() as c:
        c.execute("DELETE FROM sessoes WHERE expira_em < ?", (agora,))
        c.execute("INSERT INTO sessoes VALUES (?,?,?,?)",
                  (_hash(token), usuario_id, agora, agora + SESSAO_DIAS * 86400))
    return token


def encerrar_sessao(token: str):
    if token:
        with _conn() as c:
            c.execute("DELETE FROM sessoes WHERE token_hash = ?", (_hash(token),))


def _usuario(c, usuario_id: int):
    row = c.execute("SELECT id, email, nome, provedor, cota_mensal, criado_em FROM usuarios WHERE id = ?",
                    (usuario_id,)).fetchone()
    return dict(row) if row else None


def usuario_da_sessao(token: str):
    if not token:
        return None
    with _conn() as c:
        row = c.execute("SELECT usuario_id FROM sessoes WHERE token_hash = ? AND expira_em > ?",
                        (_hash(token), _agora())).fetchone()
        return _usuario(c, row["usuario_id"]) if row else None


def usuario_da_chave(chave: str):
    if not chave or not chave.startswith("gv_"):
        return None
    with _conn() as c:
        row = c.execute("SELECT usuario_id FROM chaves_api WHERE chave_hash = ? AND revogada = 0",
                        (_hash(chave),)).fetchone()
        if not row:
            return None
        c.execute("UPDATE chaves_api SET ultimo_uso = ? WHERE chave_hash = ?", (_agora(), _hash(chave)))
        return _usuario(c, row["usuario_id"])


def usuario_da_requisicao(request):
    """Usuário de uma requisição HTTP (FastAPI/Starlette): cookie de sessão
    do site, ou chave de API em `Authorization: Bearer gv_...`, `X-API-Key`
    ou `?chave=` (para clientes MCP que só aceitam a URL)."""
    if request is None:
        return None
    u = usuario_da_sessao(request.cookies.get(COOKIE_SESSAO))
    if u:
        return u
    auth = request.headers.get("authorization") or ""
    chave = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    chave = (chave or request.headers.get("x-api-key") or request.query_params.get("chave") or "").strip()
    if chave.startswith("gvat_"):  # token OAuth do /mcp-conta/ (src/oauth_mcp.py)
        from src import oauth_mcp
        return oauth_mcp.usuario_do_token(chave)
    return usuario_da_chave(chave)


def excluir_usuario(usuario_id: int):
    with _conn() as c:
        c.execute("PRAGMA foreign_keys=ON")
        for t in ("sessoes", "chaves_api", "consumo"):
            c.execute(f"DELETE FROM {t} WHERE usuario_id = ?", (usuario_id,))
        email = c.execute("SELECT email FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if email:
            c.execute("DELETE FROM links_email WHERE email = ?", (email["email"],))
            c.execute("DELETE FROM envios_email WHERE email = ?", (email["email"],))
        c.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))


# ---------------------------------------------------------------- chaves de API

def criar_chave(usuario_id: int, nome: str = None) -> str:
    with _conn() as c:
        ativas = c.execute("SELECT COUNT(*) FROM chaves_api WHERE usuario_id = ? AND revogada = 0",
                           (usuario_id,)).fetchone()[0]
        if ativas >= MAX_CHAVES:
            raise ValueError(f"Limite de {MAX_CHAVES} chaves ativas. Revogue uma antes de criar outra.")
        chave = "gv_" + secrets.token_urlsafe(30)
        c.execute("INSERT INTO chaves_api (chave_hash, usuario_id, prefixo, nome, criado_em) VALUES (?,?,?,?,?)",
                  (_hash(chave), usuario_id, chave[:10], (nome or "").strip()[:60] or None, _agora()))
    return chave


def listar_chaves(usuario_id: int) -> list:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT prefixo, nome, criado_em, ultimo_uso FROM chaves_api "
            "WHERE usuario_id = ? AND revogada = 0 ORDER BY criado_em", (usuario_id,))]


def revogar_chave(usuario_id: int, prefixo: str) -> bool:
    with _conn() as c:
        cur = c.execute("UPDATE chaves_api SET revogada = 1 WHERE usuario_id = ? AND prefixo = ? AND revogada = 0",
                        (usuario_id, prefixo))
        return cur.rowcount > 0


# ---------------------------------------------------------------- cota

def cota_do_usuario(usuario: dict) -> int:
    return usuario.get("cota_mensal") if usuario.get("cota_mensal") is not None else COTA_MENSAL


def consumir(usuario: dict, cnpj: str, origem: str) -> dict:
    """Registra a consulta do relatório. Devolve {ok, usados, cota, mes,
    novo}. Mesmo CNPJ no mesmo mês não conta de novo."""
    mes = mes_atual()
    cota = cota_do_usuario(usuario)
    with _lock, _conn() as c:
        ja = c.execute("SELECT 1 FROM consumo WHERE usuario_id = ? AND mes = ? AND cnpj = ?",
                       (usuario["id"], mes, cnpj)).fetchone()
        usados = c.execute("SELECT COUNT(*) FROM consumo WHERE usuario_id = ? AND mes = ?",
                           (usuario["id"], mes)).fetchone()[0]
        if ja:
            return {"ok": True, "usados": usados, "cota": cota, "mes": mes, "novo": False}
        if usados >= cota:
            return {"ok": False, "usados": usados, "cota": cota, "mes": mes, "novo": False}
        c.execute("INSERT INTO consumo VALUES (?,?,?,?,?)", (usuario["id"], mes, cnpj, origem, _agora()))
        return {"ok": True, "usados": usados + 1, "cota": cota, "mes": mes, "novo": True}


def estornar(usuario: dict, cnpj: str, mes: str):
    """Devolve a cota de um relatório que falhou depois de cobrado."""
    with _lock, _conn() as c:
        c.execute("DELETE FROM consumo WHERE usuario_id = ? AND mes = ? AND cnpj = ?", (usuario["id"], mes, cnpj))


def uso_do_mes(usuario: dict) -> dict:
    mes = mes_atual()
    with _conn() as c:
        consultas = [dict(r) for r in c.execute(
            "SELECT cnpj, origem, criado_em FROM consumo WHERE usuario_id = ? AND mes = ? ORDER BY criado_em DESC",
            (usuario["id"], mes))]
    return {"mes": mes, "cota": cota_do_usuario(usuario), "usados": len(consultas), "consultas": consultas}


# ---------------------------------------------------------------- login por e-mail

def criar_link_email(email: str, ip: str) -> str:
    agora = _agora()
    with _lock, _conn() as c:
        c.execute("DELETE FROM envios_email WHERE em < ?", (agora - 3600,))
        c.execute("DELETE FROM links_email WHERE expira_em < ?", (agora,))
        por_email = c.execute("SELECT COUNT(*) FROM envios_email WHERE email = ?", (email,)).fetchone()[0]
        por_ip = c.execute("SELECT COUNT(*) FROM envios_email WHERE ip = ?", (ip,)).fetchone()[0]
        if por_email >= ENVIOS_POR_EMAIL_HORA or por_ip >= ENVIOS_POR_IP_HORA:
            raise LimiteEnvio()
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO links_email VALUES (?,?,?,0)", (_hash(token), email, agora + LINK_MINUTOS * 60))
        c.execute("INSERT INTO envios_email VALUES (?,?,?)", (email, ip, agora))
    return token


def usar_link_email(token: str):
    """E-mail do link, se válido; o link só vale uma vez."""
    if not token:
        return None
    with _lock, _conn() as c:
        row = c.execute("SELECT email FROM links_email WHERE token_hash = ? AND usado = 0 AND expira_em > ?",
                        (_hash(token), _agora())).fetchone()
        if not row:
            return None
        c.execute("UPDATE links_email SET usado = 1 WHERE token_hash = ?", (_hash(token),))
        return row["email"]


def enviar_email(destino: str, assunto: str, html: str, texto: str):
    if EMAIL_PROVIDER == "brevo":
        m = re.match(r"^\s*(.*?)\s*<([^>]+)>\s*$", EMAIL_FROM)
        remetente = {"name": m.group(1) or "Empresas GV", "email": m.group(2)} if m else {"email": EMAIL_FROM}
        r = httpx.post("https://api.brevo.com/v3/smtp/email", timeout=20,
                       headers={"api-key": EMAIL_API_KEY, "accept": "application/json"},
                       json={"sender": remetente, "to": [{"email": destino}], "subject": assunto,
                             "htmlContent": html, "textContent": texto})
    elif EMAIL_PROVIDER == "resend":
        r = httpx.post("https://api.resend.com/emails", timeout=20,
                       headers={"Authorization": f"Bearer {EMAIL_API_KEY}"},
                       json={"from": EMAIL_FROM, "to": [destino], "subject": assunto, "html": html, "text": texto})
    else:
        raise RuntimeError("envio de e-mail não configurado")
    r.raise_for_status()


# ---------------------------------------------------------------- Google OAuth

def url_google(state: str, redirect_uri: str) -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": GOOGLE_CLIENT_ID, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": "openid email profile", "state": state, "prompt": "select_account",
    })


def usuario_google(code: str, redirect_uri: str):
    """(email, nome) do Google para o código da volta do login, ou None."""
    tok = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
        "code": code, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    if tok.status_code != 200:
        return None
    info = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", timeout=20,
                     headers={"Authorization": f"Bearer {tok.json().get('access_token')}"})
    if info.status_code != 200:
        return None
    d = info.json()
    email = normalizar_email(d.get("email"))
    if not email or not d.get("email_verified"):
        return None
    return email, (d.get("name") or "").strip()[:120] or None


# ---------------------------------------------------------------- Pix (doação)

def _tlv(ident: str, valor: str) -> str:
    return f"{ident}{len(valor):02d}{valor}"


def _crc16(dados: str) -> str:
    crc = 0xFFFF
    for b in dados.encode():
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def pix_copia_e_cola(chave: str, nome: str, cidade: str, txid: str = "***") -> str:
    """BR Code estático (padrão EMV do Banco Central), sem valor fixo: quem
    doa escolhe o valor no app do banco."""
    conta = _tlv("00", "br.gov.bcb.pix") + _tlv("01", chave)
    corpo = (_tlv("00", "01") + _tlv("26", conta) + _tlv("52", "0000") + _tlv("53", "986")
             + _tlv("58", "BR") + _tlv("59", nome[:25]) + _tlv("60", cidade[:15])
             + _tlv("62", _tlv("05", txid)) + "6304")
    return corpo + _crc16(corpo)
