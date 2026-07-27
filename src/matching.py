"""
Matching entre registros de fontes externas (sanções, processos, infrações
ambientais) e a base de empresas já carregada — usado quando a fonte não
traz o CNPJ diretamente, só a razão social.

Estratégia:
  1. Match direto por CNPJ (quando existe na fonte) — sempre prioritário
     e marcado como match_confianca='direto'.
  2. Fallback: fuzzy match por razão social + município usando
     rapidfuzz.fuzz.token_sort_ratio, aceito apenas acima do threshold
     definido em config.FUZZY_MATCH_THRESHOLD, marcado como 'fuzzy'.

Match fuzzy é a etapa mais frágil do pipeline — recomenda-se revisão
manual de amostra antes de tratar como dado definitivo.
"""
from rapidfuzz import fuzz, process

import config


def normalizar_cnpj(cnpj_raw: str) -> str:
    """Remove máscara e mantém só dígitos."""
    if not cnpj_raw:
        return ""
    return "".join(c for c in cnpj_raw if c.isdigit())


def match_por_cnpj(cnpj_raw: str, cnpjs_validos: set) -> str | None:
    cnpj = normalizar_cnpj(cnpj_raw)
    return cnpj if cnpj in cnpjs_validos else None


def match_fuzzy_por_razao_social(razao_social_busca: str, base_empresas: list) -> tuple:
    """
    base_empresas: lista de tuplas (cnpj, razao_social) já carregadas do banco.
    Retorna (cnpj_encontrado, score) ou (None, 0) se abaixo do threshold.
    """
    if not razao_social_busca or not base_empresas:
        return None, 0

    nomes = [r[1] for r in base_empresas]
    resultado = process.extractOne(
        razao_social_busca, nomes, scorer=fuzz.token_sort_ratio
    )
    if resultado is None:
        return None, 0

    nome_encontrado, score, idx = resultado
    if score >= config.FUZZY_MATCH_THRESHOLD:
        return base_empresas[idx][0], score
    return None, score
