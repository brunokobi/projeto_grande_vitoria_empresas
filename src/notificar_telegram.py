"""Notifica o dono do projeto via Telegram a cada visita no dashboard.

Roda em background (FastAPI BackgroundTasks) — nunca atrasa o carregamento
da página — e falha em silêncio: um erro na geolocalização ou no Telegram
não pode derrubar o dashboard. Se TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID não
estiverem configurados (config.py), a função só retorna sem fazer nada.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import config

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
# ipapi.co tem limite gratuito muito curto (rate-limita rápido em uso real);
# ipwho.is não pede chave e aguenta bem mais volume de graça.
GEOLOCALIZACAO_URL = "https://ipwho.is/{ip}"
_PREFIXOS_LOCAIS = ("127.", "10.", "192.168.", "172.16.", "::1")


def _resolver_ip(ip_forwarded, client_host):
    """Atrás do Traefik (Coolify) o IP real do visitante vem no cabeçalho
    X-Forwarded-For — request.client.host seria o IP interno do proxy."""
    if ip_forwarded:
        return ip_forwarded.split(",")[0].strip()
    return client_host or "desconhecido"


def _geolocalizar(ip: str) -> str:
    if not ip or ip.startswith(_PREFIXOS_LOCAIS) or ip == "desconhecido":
        return "IP local/interno"
    try:
        with urllib.request.urlopen(GEOLOCALIZACAO_URL.format(ip=ip), timeout=4) as resp:
            d = json.load(resp)
        if not d.get("success", True):
            return ip
        partes = [p for p in (d.get("city"), d.get("region"), d.get("country")) if p]
        return ", ".join(partes) if partes else ip
    except Exception:
        return ip


def notificar_visita_dashboard(ip_forwarded, client_host):
    """Dispara a notificação de visita. Chamar via BackgroundTasks."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    ip = _resolver_ip(ip_forwarded, client_host)
    local = _geolocalizar(ip)
    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
    texto = (
        "🌐 Nova visita no Dashboard de Empresas\n"
        f"📍 {local}\n"
        f"🔢 IP: {ip}\n"
        f"🕒 {agora} (horário de Brasília)"
    )
    body = json.dumps({"chat_id": config.TELEGRAM_CHAT_ID, "text": texto}).encode("utf-8")
    req = urllib.request.Request(
        TELEGRAM_API_URL.format(token=config.TELEGRAM_BOT_TOKEN),
        data=body, headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def enviar(texto: str):
    """Envia uma mensagem qualquer (em thread própria: não atrasa a resposta,
    falha em silêncio). Sem TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID, não faz nada."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    import threading

    def _go():
        body = json.dumps({"chat_id": config.TELEGRAM_CHAT_ID, "text": texto}).encode("utf-8")
        req = urllib.request.Request(TELEGRAM_API_URL.format(token=config.TELEGRAM_BOT_TOKEN),
                                     data=body, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


def _agora() -> str:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")


def mascarar_email(email: str) -> str:
    """fulano.silva@gmail.com -> fu***@gmail.com (o aviso não precisa do e-mail inteiro)."""
    nome, _, dominio = (email or "").partition("@")
    return (nome[:2] + "***@" + dominio) if dominio else "***"


def notificar_cadastro(email: str, provedor: str, total_contas: int):
    enviar("🆕 Novo cadastro no Empresas GV\n"
           f"👤 {mascarar_email(email)} (via {'Google' if provedor == 'google' else 'link por e-mail'})\n"
           f"📊 Total de contas: {total_contas}\n"
           f"🕒 {_agora()} (horário de Brasília)")


_ACOES_DOACAO = {
    "abriu": "💛 Alguém abriu a tela de doação",
    "copiou_pix": "💸 Alguém COPIOU o Pix copia e cola",
    "sponsors": "🐙 Alguém clicou no GitHub Sponsors",
}


def notificar_doacao(acao: str, ip_forwarded, client_host):
    if acao not in _ACOES_DOACAO:
        return
    local = _geolocalizar(_resolver_ip(ip_forwarded, client_host))
    enviar(f"{_ACOES_DOACAO[acao]}\n📍 {local}\n🕒 {_agora()} (horário de Brasília)\n"
           "(clique não confirma pagamento: confira o extrato do Pix/Sponsors)")
