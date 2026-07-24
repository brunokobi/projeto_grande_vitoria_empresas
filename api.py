"""
API REST + Dashboard do dataset de empresas da Grande Vitória (FastAPI).

- Serve o dashboard web (dashboard/index.html) na raiz `/`.
- Expõe o dataset por HTTP (mesma lógica de consulta do MCP,
  src/dataset_queries) e permite exportar a lista filtrada em Excel e PDF.

Rodar:
    uvicorn api:app --reload      # abre em http://localhost:8000
Docs da API: http://localhost:8000/docs
"""
import io

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse

import config
from src import dataset_queries

app = FastAPI(
    title="Empresas da Grande Vitória — API + Dashboard",
    description="Dataset consolidado de empresas ativas da Grande Vitória (ES).",
    version="2.0.0",
)

DASHBOARD_HTML = config.BASE_DIR / "dashboard" / "index.html"


# --------------------------------------------------------------------------
# Filtros compartilhados entre /empresas e os exports
# --------------------------------------------------------------------------
def filtros_comuns(
    municipio: str = Query(None),
    cnae: str = Query(None),
    cnae_prefix: str = Query(None, description="Prefixo CNAE = segmento (2 dígitos)"),
    porte: str = Query(None),
    regime_tributario: str = Query(None),
    texto: str = Query(None),
    socio: str = Query(None, description="Nome (ou parte) do sócio"),
    tem_pendencia: bool = Query(None),
    com_telefone: bool = Query(None),
    com_email: bool = Query(None),
    com_whatsapp: bool = Query(None),
    com_rede_social: bool = Query(None),
    com_processos: bool = Query(None, description="Só empresas com processos judiciais"),
    com_sancoes: bool = Query(None, description="Só empresas com sanções"),
    com_ambiental: bool = Query(None, description="Só empresas com infração ambiental"),
    com_divida: bool = Query(None, description="Só empresas com dívida ativa"),
    com_trabalho_escravo: bool = Query(None, description="Só empresas na Lista Suja do trabalho escravo (MTE)"),
    com_cepim: bool = Query(None, description="Só empresas no CEPIM (impedidas de receber recursos federais)"),
    com_leniencia: bool = Query(None, description="Só empresas com acordo de leniência"),
    capital_min: float = Query(None),
    capital_max: float = Query(None),
    ordenar_por: str = Query("razao_social"),
) -> dict:
    return dict(
        municipio=municipio, cnae=cnae, cnae_prefix=cnae_prefix, porte=porte,
        regime_tributario=regime_tributario, texto=texto, socio=socio, tem_pendencia=tem_pendencia,
        com_telefone=com_telefone, com_email=com_email, com_whatsapp=com_whatsapp,
        com_rede_social=com_rede_social, com_processos=com_processos,
        com_sancoes=com_sancoes, com_ambiental=com_ambiental, com_divida=com_divida,
        com_trabalho_escravo=com_trabalho_escravo, com_cepim=com_cepim, com_leniencia=com_leniencia,
        capital_min=capital_min, capital_max=capital_max, ordenar_por=ordenar_por,
    )


# --------------------------------------------------------------------------
# Dashboard + API JSON
# --------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def dashboard():
    if DASHBOARD_HTML.exists():
        return FileResponse(DASHBOARD_HTML)
    return JSONResponse({"erro": "dashboard/index.html não encontrado"}, status_code=404)


@app.get("/api", summary="Índice da API")
def indice_api():
    return {
        "endpoints": {
            "GET /estatisticas": "Panorama geral",
            "GET /segmentos": "Segmentos (divisões CNAE) com contagem",
            "GET /empresas": "Busca com filtros",
            "GET /empresas/{cnpj}": "Visão 360º",
            "GET /export/empresas.xlsx": "Lista filtrada em Excel",
            "GET /export/empresas.pdf": "Lista filtrada em PDF",
        }
    }


@app.get("/estatisticas", summary="Panorama geral do dataset")
def get_estatisticas():
    return dataset_queries.estatisticas()


@app.get("/segmentos", summary="Segmentos (divisões CNAE) com contagem")
def get_segmentos():
    return dataset_queries.segmentos()


@app.get("/empresas", summary="Busca empresas com filtros de prospecção")
def get_empresas(
    filtros: dict = Depends(filtros_comuns),
    limite: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return dataset_queries.buscar_empresas(limite=limite, offset=offset, **filtros)


@app.get("/mapa", summary="Pontos geocodificados (lat/long) para o mapa, com os mesmos filtros")
def get_mapa(
    filtros: dict = Depends(filtros_comuns),
    limite: int = Query(20000, ge=1, le=50000),
):
    return dataset_queries.pontos_mapa(limite=limite, **filtros)


@app.get("/empresas/{cnpj}", summary="Visão 360º de uma empresa pelo CNPJ")
def get_empresa(cnpj: str):
    resultado = dataset_queries.obter_empresa(cnpj)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"CNPJ {cnpj} não encontrado.")
    return resultado


@app.get("/classificar", summary="Classifica/pontua empresas por objetivo de prospecção")
def get_classificar(
    objetivo: str = Query("generico"),
    pref_telefone: bool = Query(None),
    pref_email: bool = Query(None),
    pref_whatsapp: bool = Query(None),
    pref_rede: bool = Query(None),
    portes: list[str] = Query(None),
    presenca: str = Query("indiferente"),
    fiscal: str = Query("indiferente"),
    municipio: str = Query(None),
    cnae_prefix: str = Query(None),
    texto: str = Query(None),
    capital_min: float = Query(None),
    capital_max: float = Query(None),
    limite: int = Query(50, ge=1, le=500),
):
    return dataset_queries.classificar_empresas(
        objetivo=objetivo, pref_telefone=pref_telefone, pref_email=pref_email,
        pref_whatsapp=pref_whatsapp, pref_rede=pref_rede, portes=portes,
        presenca=presenca, fiscal=fiscal, municipio=municipio,
        cnae_prefix=cnae_prefix, texto=texto, capital_min=capital_min,
        capital_max=capital_max, limite=limite,
    )


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------
_COLUNAS_EXPORT = [
    ("cnpj", "CNPJ"), ("razao_social", "Razão social"),
    ("nome_fantasia", "Nome fantasia"), ("municipio", "Município"),
    ("bairro", "Bairro"), ("cnae_principal", "CNAE"),
    ("cnae_desc", "Atividade (CNAE)"), ("porte", "Porte"),
    ("capital_social", "Capital social"), ("regime_tributario", "Regime"),
    ("telefone", "Telefone"), ("email", "E-mail"), ("whatsapp", "WhatsApp"),
    ("site", "Site"), ("instagram", "Instagram"), ("facebook", "Facebook"),
    ("linkedin", "LinkedIn"), ("tem_pendencia", "Pendência"),
]


@app.get("/export/empresas.xlsx", summary="Exporta a lista filtrada em Excel")
def export_xlsx(filtros: dict = Depends(filtros_comuns)):
    import pandas as pd
    dados = dataset_queries.exportar_empresas(max_linhas=20000, **filtros)
    df = pd.DataFrame(dados, columns=[c for c, _ in _COLUNAS_EXPORT])
    df = df.rename(columns=dict(_COLUNAS_EXPORT))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Empresas")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="empresas_grande_vitoria.xlsx"'},
    )


@app.get("/export/empresas.pdf", summary="Exporta a lista filtrada em PDF")
def export_pdf(filtros: dict = Depends(filtros_comuns)):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    LIMITE_PDF = 1500
    dados = dataset_queries.exportar_empresas(max_linhas=LIMITE_PDF, **filtros)

    verde = colors.HexColor("#00c853")
    cabecalho = ["CNPJ", "Razão social", "Município", "CNAE", "Telefone", "E-mail", "Pend."]

    def corta(v, n):
        s = "" if v is None else str(v)
        return s if len(s) <= n else s[: n - 1] + "…"

    linhas = [cabecalho]
    for d in dados:
        linhas.append([
            corta(d.get("cnpj"), 14), corta(d.get("razao_social"), 38),
            corta(d.get("municipio"), 12), corta(d.get("cnae_principal"), 8),
            corta(d.get("telefone"), 15), corta(d.get("email"), 30),
            "SIM" if d.get("tem_pendencia") else "—",
        ])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=14 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    titulo = Paragraph(
        f"<b>Empresas da Grande Vitória (ES)</b> — {len(dados)} empresas"
        + (f" (limitado a {LIMITE_PDF})" if len(dados) >= LIMITE_PDF else ""),
        styles["Title"])
    tabela = Table(linhas, repeatRows=1,
                   colWidths=[26 * mm, 78 * mm, 26 * mm, 18 * mm, 30 * mm, 62 * mm, 14 * mm])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), verde),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eafaf0")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c8e6d4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    doc.build([titulo, Spacer(1, 6), tabela])
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="empresas_grande_vitoria.pdf"'},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
