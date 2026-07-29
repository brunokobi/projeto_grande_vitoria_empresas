"""
Configuração do repositório de CONSUMO (dashboard + API + MCP).

Só o necessário para consultar o dataset. A parte de extração/ETL (fontes,
chaves, URLs) fica no repositório privado de extração.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "grande_vitoria.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Checkpoints do pipeline de extração (progresso retomável de etapas longas,
# ex.: djen/datajud/geo). Perdido no merge do repo de consumo com o de
# extração — as demais chaves de config do pipeline (URLs de fontes, chaves
# de API) continuam só no repositório de extração.
CHECKPOINT_DIR = BASE_DIR / "data" / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# Segmentos de mercado (divisão CNAE = 2 primeiros dígitos do CNAE principal)
# usados no filtro de "segmento" do dashboard. Ordem por relevância na região.
SEGMENTOS_CNAE = {
    "47": "Comércio varejista",
    "56": "Restaurantes e alimentação",
    "43": "Construção — serviços especializados",
    "41": "Construção de edifícios",
    "49": "Transporte terrestre",
    "53": "Correio e entregas",
    "96": "Serviços pessoais (beleza, estética)",
    "82": "Serviços administrativos e de escritório",
    "85": "Educação",
    "86": "Saúde",
    "73": "Publicidade e marketing",
    "45": "Veículos — comércio e reparação",
    "46": "Comércio atacadista",
    "81": "Serviços para edifícios e paisagismo",
    "62": "Tecnologia da informação (software)",
    "68": "Atividades imobiliárias",
    "69": "Serviços jurídicos e contábeis",
    "71": "Arquitetura e engenharia",
    "10": "Indústria de alimentos",
    "94": "Organizações associativas",
}
