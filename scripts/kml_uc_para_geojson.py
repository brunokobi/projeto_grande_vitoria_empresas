"""
Converte o KML de Unidades de Conservação / Zonas de Amortecimento (IEMA-ES)
pra GeoJSON, no mesmo padrão de reference/bairros_grande_vitoria.geojson e
reference/municipios_grande_vitoria.geojson (mesma pasta, mesmo uso: camada
estática servida pelo dashboard).

Uso:
    python3 scripts/kml_uc_para_geojson.py caminho/do/arquivo.kml

Não usa fastkml/GDAL (nenhum dos dois está instalado, e não compensa
instalar só pra isso) -- KML é XML simples, dá pra extrair Placemark/
Polygon/MultiGeometry com xml.etree.ElementTree (stdlib).

Se a UC vier em EPSG diferente de 4326 no arquivo, ajuste _CRS_ORIGEM
abaixo -- na prática a maioria dos KML já vem em WGS84 (KML é sempre
lon,lat,alt por especificação, então normalmente não precisa reprojetar).
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def _coords_para_lista(texto_coords: str) -> list:
    """KML: 'lon,lat[,alt] lon,lat[,alt] ...' -> [[lon,lat], ...]
    (descarta altitude -- não usamos elevação no mapa 2D)."""
    pontos = []
    for grupo in texto_coords.split():
        partes = grupo.split(",")
        if len(partes) >= 2:
            pontos.append([float(partes[0]), float(partes[1])])
    return pontos


def _parse_polygon(el) -> dict:
    anel_ext = el.find(".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", _NS)
    aneis_int = el.findall(".//kml:innerBoundaryIs/kml:LinearRing/kml:coordinates", _NS)
    coords = [_coords_para_lista(anel_ext.text)]
    for anel in aneis_int:
        coords.append(_coords_para_lista(anel.text))
    return {"type": "Polygon", "coordinates": coords}


def _parse_geometria(placemark) -> dict | None:
    poly = placemark.find("kml:Polygon", _NS)
    if poly is not None:
        return _parse_polygon(poly)
    multi = placemark.find("kml:MultiGeometry", _NS)
    if multi is not None:
        polys = [_parse_polygon(p) for p in multi.findall("kml:Polygon", _NS)]
        if polys:
            return {"type": "MultiPolygon", "coordinates": [p["coordinates"] for p in polys]}
    return None


def _parse_extended_data(placemark) -> dict:
    """<ExtendedData><Data name="X"><value>Y</value></Data>...</ExtendedData>
    -- é assim que a maioria dos exports de geoportal (ArcGIS/QGIS) guarda
    os atributos da tabela original dentro do KML."""
    props = {}
    ext = placemark.find("kml:ExtendedData", _NS)
    if ext is None:
        return props
    for data in ext.findall("kml:Data", _NS):
        nome = data.get("name")
        valor_el = data.find("kml:value", _NS)
        if nome and valor_el is not None:
            props[nome] = (valor_el.text or "").strip()
    return props


def kml_para_geojson(caminho_kml: Path) -> dict:
    tree = ET.parse(caminho_kml)
    root = tree.getroot()
    features = []
    for placemark in root.findall(".//kml:Placemark", _NS):
        geom = _parse_geometria(placemark)
        if geom is None:
            continue  # Placemark sem geometria de área (ponto/linha solto) -- ignora
        nome_el = placemark.find("kml:name", _NS)
        descr_el = placemark.find("kml:description", _NS)
        props = _parse_extended_data(placemark)
        props.setdefault("nome", (nome_el.text or "").strip() if nome_el is not None else "")
        if descr_el is not None and descr_el.text:
            props.setdefault("descricao", descr_el.text.strip())
        features.append({"type": "Feature", "properties": props, "geometry": geom})
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: python3 scripts/kml_uc_para_geojson.py caminho/do/arquivo.kml")
        sys.exit(1)
    caminho = Path(sys.argv[1])
    gj = kml_para_geojson(caminho)
    print(f"{len(gj['features'])} unidades de conservação extraídas")
    if gj["features"]:
        print("exemplo de properties:", gj["features"][0]["properties"])
    saida = Path(__file__).resolve().parent.parent / "reference" / "unidades_conservacao_es.geojson"
    saida.write_text(json.dumps(gj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"salvo em {saida} ({saida.stat().st_size / 1024:.0f} KB)")
