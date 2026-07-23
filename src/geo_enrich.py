"""
Enriquecimento geográfico via OpenStreetMap Nominatim — gratuito, sem
necessidade de cartão de crédito ou chave de API.

Trade-off aceito (em vez de Google Places, que exige cartão):
  - NÃO traz telefone atualizado, site, avaliação nem horário de
    funcionamento — só geocodificação (latitude/longitude) a partir do
    endereço já presente na base da Receita Federal.
  - Rate limit rígido de 1 requisição/segundo — é a política de uso do
    servidor público do Nominatim, não um limite arbitrário nosso.
    Ver: https://operations.osmfoundation.org/policies/nominatim/
  - Para bases grandes (dezenas de milhares de empresas), a 1 req/s isso
    é lento (ex.: 50.000 empresas ~ 14h rodando). Se isso for um problema,
    a alternativa dentro da política de uso é subir uma instância própria
    do Nominatim via Docker (https://github.com/mediagis/nominatim-docker)
    e apontar NOMINATIM_URL para o seu próprio servidor, sem rate limit
    externo.
  - Exige um User-Agent identificando a aplicação (não é opcional pela
    política de uso) — configurado em NOMINATIM_USER_AGENT.
"""
import time

import requests

import config
from src import db_utils, checkpoint

CHECKPOINT_NAME = "geocode_processados"


def _geocodificar(endereco: str) -> dict:
    """Retorna dict com lat/lon/osm_id ou None se não encontrado."""
    params = {"q": endereco, "format": "json", "limit": 1}
    headers = {"User-Agent": config.NOMINATIM_USER_AGENT}
    resp = requests.get(config.NOMINATIM_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    resultados = resp.json()
    if not resultados:
        return None
    r = resultados[0]
    return {
        "lat": float(r["lat"]),
        "lon": float(r["lon"]),
        "osm_id": r.get("osm_id"),
        "display_name": r.get("display_name"),
    }


def executar(limite_cnpjs: int = None):
    with db_utils.get_conn() as conn:
        cur = conn.execute(
            "SELECT cnpj, logradouro, numero, bairro, municipio, uf FROM empresas"
        )
        empresas = cur.fetchall()

    processados = set(checkpoint.carregar(CHECKPOINT_NAME))
    pendentes = [e for e in empresas if e["cnpj"] not in processados]
    if limite_cnpjs:
        pendentes = pendentes[:limite_cnpjs]

    print(f"[geo_enrich] {len(pendentes)} empresas pendentes de geocodificação "
          f"(~{len(pendentes) * config.NOMINATIM_RATE_LIMIT_SLEEP_SECONDS / 3600:.1f}h estimadas).")

    # Commit + checkpoint em lote a cada N — durável: se o processo cair, o
    # que já foi gravado no banco continua lá e o checkpoint bate com ele
    # (perde-se no máximo N itens, que são refeitos). NÃO usar uma transação
    # única pro loop inteiro (perderia tudo num crash antes do fim).
    LOTE = 100
    with db_utils.get_conn() as conn:
        for i, empresa in enumerate(pendentes):
            endereco = (
                f"{empresa['logradouro']}, {empresa['numero']} - "
                f"{empresa['bairro']}, {empresa['municipio']} - {empresa['uf']}, Brasil"
            )
            try:
                geo = _geocodificar(endereco)
                if geo:
                    conn.execute(
                        """INSERT INTO enriquecimento_places
                           (cnpj_empresa, place_id, latitude, longitude, data_enriquecimento)
                           VALUES (?, ?, ?, ?, ?)
                           ON CONFLICT(cnpj_empresa) DO UPDATE SET
                             place_id=excluded.place_id,
                             latitude=excluded.latitude,
                             longitude=excluded.longitude,
                             data_enriquecimento=excluded.data_enriquecimento
                        """,
                        (
                            empresa["cnpj"], str(geo["osm_id"]), geo["lat"], geo["lon"],
                            time.strftime("%Y-%m-%d %H:%M:%S"),
                        ),
                    )
            except requests.RequestException as e:
                print(f"[geo_enrich] Erro em {empresa['cnpj']}: {e}")

            processados.add(empresa["cnpj"])
            time.sleep(config.NOMINATIM_RATE_LIMIT_SLEEP_SECONDS)

            if (i + 1) % LOTE == 0:
                conn.commit()
                checkpoint.salvar(CHECKPOINT_NAME, processados)
                print(f"[geo_enrich] {i+1}/{len(pendentes)} empresas geocodificadas (salvo).")
        conn.commit()
    checkpoint.salvar(CHECKPOINT_NAME, processados)

    print("[geo_enrich] Geocodificação concluída.")


if __name__ == "__main__":
    executar()
