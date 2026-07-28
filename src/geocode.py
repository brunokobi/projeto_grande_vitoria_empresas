"""
Geocodificação de endereço sob demanda (Nominatim/OSM), server-side.

Usado tanto pelo endpoint /geocode da API (fallback do mapa, quando a
empresa ainda não foi geocodificada pela etapa `geo`) quanto pela ferramenta
MCP `buscar_empresas_perto` (resolve um endereço em texto pra lat/lon antes
de buscar por raio).
"""
import json
import urllib.parse
import urllib.request

_USER_AGENT = "grande-vitoria-empresas-dashboard/1.0 (geocodificacao sob demanda)"


def resolver_endereco(q: str) -> dict:
    """Resolve um endereço/texto livre em coordenadas via Nominatim.
    Retorna {'lat': float, 'lon': float} ou {'lat': None, 'lon': None} se
    não encontrar (ou se o serviço falhar)."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "br"})
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            arr = json.load(resp)
    except Exception:
        return {"lat": None, "lon": None}
    if arr:
        return {"lat": float(arr[0]["lat"]), "lon": float(arr[0]["lon"])}
    return {"lat": None, "lon": None}
