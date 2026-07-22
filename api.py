"""
API REST do dataset de empresas da Grande Vitória (FastAPI).

Expõe o dataset consolidado por HTTP, para consumir de qualquer linguagem
ou ferramenta. Mesma lógica de consulta do servidor MCP (src/dataset_queries).

Rodar:
    uvicorn api:app --reload
    # ou: python api.py

Docs interativas automáticas em:
    http://localhost:8000/docs      (Swagger UI)
    http://localhost:8000/redoc     (ReDoc)
"""
from fastapi import FastAPI, HTTPException, Query

from src import dataset_queries

app = FastAPI(
    title="Empresas da Grande Vitória — API",
    description=(
        "Consulta do dataset consolidado de empresas ativas da Grande "
        "Vitória (ES), cruzando dados cadastrais, jurídicos, sanções, "
        "dívida ativa e infrações ambientais de fontes públicas."
    ),
    version="1.0.0",
)


@app.get("/", summary="Índice da API")
def raiz():
    return {
        "dataset": "Empresas ativas da Grande Vitória (ES)",
        "endpoints": {
            "GET /estatisticas": "Panorama geral do dataset",
            "GET /empresas": "Busca com filtros de prospecção",
            "GET /empresas/{cnpj}": "Visão 360º de uma empresa",
            "GET /docs": "Documentação interativa (Swagger)",
        },
    }


@app.get("/estatisticas", summary="Panorama geral do dataset")
def get_estatisticas():
    return dataset_queries.estatisticas()


@app.get("/empresas", summary="Busca empresas com filtros de prospecção")
def get_empresas(
    municipio: str = Query(None, description="Vitória, Vila Velha, Serra, Cariacica, Viana, Guarapari, Fundão"),
    cnae: str = Query(None, description="Código CNAE (principal ou secundário)"),
    porte: str = Query(None),
    regime_tributario: str = Query(None, description='Ex.: "MEI", "Simples Nacional", "Normal"'),
    texto: str = Query(None, description="Parte da razão social ou nome fantasia"),
    tem_pendencia: bool = Query(None, description="True=só com pendência; False=só limpas"),
    com_telefone: bool = Query(None),
    com_email: bool = Query(None),
    capital_min: float = Query(None),
    capital_max: float = Query(None),
    ordenar_por: str = Query("razao_social"),
    limite: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return dataset_queries.buscar_empresas(
        municipio=municipio, cnae=cnae, porte=porte,
        regime_tributario=regime_tributario, texto=texto,
        tem_pendencia=tem_pendencia, com_telefone=com_telefone,
        com_email=com_email, capital_min=capital_min, capital_max=capital_max,
        ordenar_por=ordenar_por, limite=limite, offset=offset,
    )


@app.get("/empresas/{cnpj}", summary="Visão 360º de uma empresa pelo CNPJ")
def get_empresa(cnpj: str):
    resultado = dataset_queries.obter_empresa(cnpj)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"CNPJ {cnpj} não encontrado na base.")
    return resultado


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
