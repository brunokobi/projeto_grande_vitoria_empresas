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
GEOLOCALIZACAO_URL = "https://ipapi.co/{ip}/json/"
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
        if d.get("error"):
            return ip
        partes = [p for p in (d.get("city"), d.get("region"), d.get("country_name")) if p]
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
