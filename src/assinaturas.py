"""
Assinaturas pagas (planos com mais relatórios por mês), sem provedor de
pagamento: Pix na chave do mantenedor + liberação com 1 toque no Telegram.

Fluxo:
1. Usuário logado escolhe plano/período → `POST /assinatura/pedido` cria um
   pedido com código único (ex.: GVK7P3QX) e devolve o Pix copia e cola já
   com o valor e o código no identificador (txid).
2. Paga no app do banco e clica "Já paguei" → `POST /assinatura/pedido/{codigo}/paguei`
   → aviso no Telegram do mantenedor com um link assinado (HMAC).
3. O link abre `GET /admin/assinatura/{codigo}?sig=...`: uma página de
   confirmação com o botão "Ativar" (POST). Não ativa no GET: o Telegram abre
   os links sozinho para gerar a prévia.
4. Ativar grava `usuarios.plano`/`plano_ate` (30 ou 365 dias, somando ao
   vencimento atual quando é renovação do mesmo plano). A cota do plano vale
   enquanto `plano_ate` não passar (`contas.cota_do_usuario`).

Sem renovação automática: perto do vencimento a conta mostra "Renovar".
O segredo do HMAC é gerado uma vez e guardado em `contas.db` (tabela
`config`), sem variável de ambiente.
"""
import hashlib
import hmac
import io
import secrets
import time
from html import escape

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

import config
from src import contas, notificar_telegram
from src.contas_rotas import SITE_URL, _pagina

router = APIRouter()

DIAS = {"mensal": 30, "anual": 365}
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O/1/I, fácil de ler


def _db():
    c = contas._conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS assinatura_pedidos (
        codigo TEXT PRIMARY KEY,
        usuario_id INTEGER NOT NULL,
        plano TEXT NOT NULL,
        periodo TEXT NOT NULL,
        valor_centavos INTEGER NOT NULL,
        status TEXT NOT NULL,            -- aguardando | informado | ativado | recusado
        criado_em INTEGER NOT NULL,
        informado_em INTEGER,
        decidido_em INTEGER
    );
    CREATE INDEX IF NOT EXISTS ix_pedidos_usuario ON assinatura_pedidos(usuario_id);
    """)
    return c


def _segredo() -> bytes:
    with _db() as c:
        row = c.execute("SELECT valor FROM config WHERE chave = 'assinatura_hmac'").fetchone()
        if row:
            return row["valor"].encode()
        v = secrets.token_hex(32)
        c.execute("INSERT INTO config VALUES ('assinatura_hmac', ?)", (v,))
        return v.encode()


def _assinar(codigo: str) -> str:
    return hmac.new(_segredo(), codigo.encode(), hashlib.sha256).hexdigest()[:32]


def valor_centavos(plano: str, periodo: str) -> int:
    p = contas.PLANOS[plano]
    return p["mensal"] if periodo == "mensal" else p["anual_mes"] * 12


def _brl(centavos: int) -> str:
    return f"R$ {centavos // 100},{centavos % 100:02d}"


def _copia_e_cola(pedido: dict) -> str:
    return contas.pix_copia_e_cola(config.PIX_CHAVE, config.PIX_NOME, config.PIX_CIDADE,
                                   txid=pedido["codigo"], valor=pedido["valor_centavos"] / 100)


def _pedido_json(p: dict) -> dict:
    return {"codigo": p["codigo"], "plano": p["plano"], "plano_nome": contas.PLANOS[p["plano"]]["nome"],
            "periodo": p["periodo"], "valor": _brl(p["valor_centavos"]), "status": p["status"],
            "criado_em": p["criado_em"], "pix_copia_e_cola": _copia_e_cola(p),
            "pix_qrcode": f"/assinatura/pedido/{p['codigo']}/pix.svg"}


def pedidos_do_usuario(usuario_id: int, limite: int = 10) -> list:
    with _db() as c:
        return [_pedido_json(dict(r)) for r in c.execute(
            "SELECT * FROM assinatura_pedidos WHERE usuario_id = ? ORDER BY criado_em DESC LIMIT ?",
            (usuario_id, limite))]


def _usuario_logado(request: Request) -> dict:
    u = contas.usuario_da_sessao(request.cookies.get(contas.COOKIE_SESSAO))
    if not u:
        raise HTTPException(401, "Entre na sua conta para assinar um plano.")
    return u


# ---------------------------------------------------------------- público / usuário

@router.get("/planos", summary="Planos de assinatura e preços", tags=["Conta"])
def get_planos():
    return {"gratis": {"nome": "Grátis", "cota": contas.COTA_MENSAL},
            "planos": [{"codigo": k, "nome": p["nome"], "cota": p["cota"],
                        "mensal": _brl(p["mensal"]), "anual_por_mes": _brl(p["anual_mes"]),
                        "anual_total": _brl(p["anual_mes"] * 12),
                        "desconto_anual_pct": round(100 * (1 - p["anual_mes"] / p["mensal"]))}
                       for k, p in contas.PLANOS.items()],
            "pagamento": "Pix; ativação manual após conferência, normalmente em minutos (horário comercial)."}


@router.post("/assinatura/pedido", include_in_schema=False)
async def criar_pedido(request: Request):
    u = _usuario_logado(request)
    try:
        d = await request.json()
    except Exception:
        d = {}
    plano, periodo = d.get("plano"), d.get("periodo")
    if plano not in contas.PLANOS or periodo not in DIAS:
        raise HTTPException(400, "Plano ou período inválido.")
    agora = int(time.time())
    with _db() as c:
        # Reaproveita um pedido aberto do mesmo plano/período (evita pedidos duplicados ao clicar de novo).
        row = c.execute("SELECT * FROM assinatura_pedidos WHERE usuario_id = ? AND plano = ? AND periodo = ? "
                        "AND status IN ('aguardando','informado') AND criado_em > ? ORDER BY criado_em DESC LIMIT 1",
                        (u["id"], plano, periodo, agora - 3 * 86400)).fetchone()
        if row:
            return _pedido_json(dict(row))
        abertos = c.execute("SELECT COUNT(*) FROM assinatura_pedidos WHERE usuario_id = ? AND status IN "
                            "('aguardando','informado')", (u["id"],)).fetchone()[0]
        if abertos >= 3:
            raise HTTPException(429, "Você já tem pedidos em aberto. Aguarde a confirmação ou fale com o suporte.")
        codigo = "GV" + "".join(secrets.choice(_ALFABETO) for _ in range(6))
        c.execute("INSERT INTO assinatura_pedidos (codigo, usuario_id, plano, periodo, valor_centavos, status, criado_em) "
                  "VALUES (?,?,?,?,?,'aguardando',?)", (codigo, u["id"], plano, periodo, valor_centavos(plano, periodo), agora))
        row = c.execute("SELECT * FROM assinatura_pedidos WHERE codigo = ?", (codigo,)).fetchone()
    return _pedido_json(dict(row))


def _pedido_do_usuario(codigo: str, usuario_id: int) -> dict:
    with _db() as c:
        row = c.execute("SELECT * FROM assinatura_pedidos WHERE codigo = ? AND usuario_id = ?",
                        (codigo, usuario_id)).fetchone()
    if not row:
        raise HTTPException(404, "Pedido não encontrado.")
    return dict(row)


@router.get("/assinatura/pedido/{codigo}/pix.svg", include_in_schema=False)
def pix_pedido(codigo: str, request: Request):
    p = _pedido_do_usuario(codigo, _usuario_logado(request)["id"])
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(_copia_e_cola(p), image_factory=qrcode.image.svg.SvgPathFillImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/assinatura/pedido/{codigo}/paguei", include_in_schema=False)
def informar_pagamento(codigo: str, request: Request):
    u = _usuario_logado(request)
    p = _pedido_do_usuario(codigo, u["id"])
    if p["status"] == "ativado":
        return {"ok": True, "status": "ativado"}
    if p["status"] == "aguardando":
        with _db() as c:
            c.execute("UPDATE assinatura_pedidos SET status = 'informado', informado_em = ? WHERE codigo = ?",
                      (int(time.time()), codigo))
        link = f"{SITE_URL}/admin/assinatura/{codigo}?sig={_assinar(codigo)}"
        notificar_telegram.enviar(
            f"💰 Pagamento informado — Empresas GV\n"
            f"👤 {notificar_telegram.mascarar_email(u['email'])}\n"
            f"📦 {contas.PLANOS[p['plano']]['nome']} {p['periodo']} — {_brl(p['valor_centavos'])}\n"
            f"🔖 Código do Pix: {codigo}\n"
            f"Confira no extrato e ative: {link}")
    return {"ok": True, "status": "informado"}


# ---------------------------------------------------------------- mantenedor (link assinado do Telegram)

def _pedido_admin(codigo: str, sig: str) -> dict:
    if not sig or not hmac.compare_digest(sig, _assinar(codigo)):
        raise HTTPException(403, "Link inválido.")
    with _db() as c:
        row = c.execute("SELECT p.*, u.email, u.plano AS u_plano, u.plano_ate AS u_plano_ate FROM assinatura_pedidos p "
                        "JOIN usuarios u ON u.id = p.usuario_id WHERE p.codigo = ?", (codigo,)).fetchone()
    if not row:
        raise HTTPException(404, "Pedido não encontrado.")
    return dict(row)


@router.get("/admin/assinatura/{codigo}", include_in_schema=False)
def pagina_admin(codigo: str, sig: str = ""):
    p = _pedido_admin(codigo, sig)
    plano = contas.PLANOS[p["plano"]]
    estado = {"aguardando": "aguardando pagamento", "informado": "cliente informou que pagou",
              "ativado": "✅ já ativado", "recusado": "recusado"}[p["status"]]
    botoes = "" if p["status"] in ("ativado", "recusado") else f"""
<form method="post" action="/admin/assinatura/{escape(codigo)}"><input type="hidden" name="sig" value="{escape(sig)}">
<button type="submit" name="decisao" value="ativar">✅ Ativar plano</button>
<button type="submit" name="decisao" value="recusar" style="background:#30363d">Recusar</button></form>"""
    return _pagina("Confirmar assinatura", f"""<h1>Pedido {escape(codigo)}</h1>
<p><b>{escape(p['email'])}</b><br>{escape(plano['nome'])} {escape(p['periodo'])} — <b>{_brl(p['valor_centavos'])}</b><br>
Situação: {estado}</p>
<p style="font-size:13px">Antes de ativar, confira no app do banco se chegou um Pix de <b>{_brl(p['valor_centavos'])}</b>
com o identificador ou mensagem <b>{escape(codigo)}</b>.</p>{botoes}""")


@router.post("/admin/assinatura/{codigo}", include_in_schema=False)
def decidir_admin(codigo: str, sig: str = Form(""), decisao: str = Form("")):
    p = _pedido_admin(codigo, sig)
    if p["status"] in ("ativado", "recusado"):
        return _pagina("Já decidido", f"<h1>Pedido {escape(codigo)} já está {escape(p['status'])}</h1>")
    agora = int(time.time())
    with _db() as c:
        if decisao == "ativar":
            # Renovação do mesmo plano soma ao vencimento atual; troca de plano começa agora.
            inicio = max(agora, p["u_plano_ate"] or 0) if p["u_plano"] == p["plano"] else agora
            ate = inicio + DIAS[p["periodo"]] * 86400
            c.execute("UPDATE usuarios SET plano = ?, plano_ate = ? WHERE id = ?", (p["plano"], ate, p["usuario_id"]))
            c.execute("UPDATE assinatura_pedidos SET status = 'ativado', decidido_em = ? WHERE codigo = ?", (agora, codigo))
        else:
            c.execute("UPDATE assinatura_pedidos SET status = 'recusado', decidido_em = ? WHERE codigo = ?", (agora, codigo))
    if decisao == "ativar":
        notificar_telegram.enviar(f"✅ Plano ativado: {notificar_telegram.mascarar_email(p['email'])} — "
                                  f"{contas.PLANOS[p['plano']]['nome']} {p['periodo']} ({_brl(p['valor_centavos'])})")
        return _pagina("Ativado", f"<h1>✅ Plano ativado</h1><p>{escape(p['email'])} agora tem o plano "
                       f"{escape(contas.PLANOS[p['plano']]['nome'])} por {DIAS[p['periodo']]} dias.</p>")
    return _pagina("Recusado", f"<h1>Pedido {escape(codigo)} recusado</h1>")
