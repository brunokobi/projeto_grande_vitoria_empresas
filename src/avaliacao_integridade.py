"""
Nota de risco de integridade (0-100) — avaliação de terceiros baseada em regras
explícitas, calculada a partir dos dados já reunidos por `obter_empresa`.

Por que regras, e não o score preditivo do modelo de pesquisa: due diligence de
terceiros precisa ser EXPLICÁVEL (cada ponto com fonte e motivo) e estável
(a mesma evidência dá a mesma nota). O score preditivo continua no dossiê como
sinal auxiliar de priorização.

Estrutura (o que pontua e como se classifica) segue referências concretas:
  - GAFI/FATF — Recomendações 1 (abordagem baseada em risco), 10 (diligência
    devida do cliente), 12 (PEP) e 24 (beneficiário final); catálogo de sinais
    de alerta de interposição de pessoas ("laranjas");
  - Decreto 11.129/2022, art. 57, XIII — diligência apropriada para contratação
    e supervisão de terceiros (regulamenta a Lei Anticorrupção, 12.846/2013);
  - CGU — "Programa de Integridade: diretrizes para empresas privadas" e manual
    de avaliação (consulta a CEIS/CNEP/CEPIM, histórico de sanções, PEPs);
  - BCB Circular 3.978/2020 (PLD/FT) — classificação de risco que define o
    nível de diligência: simplificada / padrão / reforçada.

Os PESOS numéricos não vêm dessas normas (elas definem fatores e níveis, não
pontos) — são calibração deste projeto, documentada aqui e exibida junto da
nota. Cada fator é multiplicado pela força da evidência do cruzamento
(CNPJ > CPF mascarado + nome > nome + faixa etária > só nome), e sanções já
encerradas pesam menos que vigentes.
"""
from __future__ import annotations

import datetime
import math

VERSAO = "1.1 (nov/2026)"  # 1.1: risco-país do GAFI (sócio estrangeiro)

# Força da evidência por critério de cruzamento (multiplica os pontos).
FORCA_EVIDENCIA = {
    "cnpj": 1.0,
    "direto": 1.0,
    "razao_social": 0.9,
    "cpf_mascarado+nome": 0.85,
    "nome_completo+faixa_etaria": 0.7,
    "nome_completo": 0.5,
    "socio": 0.6,
}

NIVEIS = [  # (nota mínima, nível, diligência recomendada)
    (60, "Crítico", "Reforçada + análise jurídica antes de contratar"),
    (35, "Alto", "Reforçada (EDD): verificar cada apontamento na fonte e pedir esclarecimentos"),
    (15, "Moderado", "Padrão: confirmar os apontamentos relevantes"),
    (0, "Baixo", "Simplificada"),
]

DIMENSOES = {
    "listas": "Sanções e listas restritivas",
    "fiscal": "Situação fiscal",
    "judicial": "Litígios e processos",
    "ambiental": "Conformidade ambiental",
    "exposicao": "Exposição política e de governança",
    "fachada": "Indícios de interposição/fachada",
}
TETO_DIMENSAO = {"listas": 60, "fiscal": 25, "judicial": 25, "ambiental": 20, "exposicao": 20, "fachada": 25}


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def _hoje() -> str:
    return datetime.date.today().isoformat()


def _vigente(data_fim) -> bool:
    if not data_fim:
        return True
    return str(data_fim)[:10] >= _hoje()


class _Avaliacao:
    def __init__(self):
        self.fatores = []
        self.impeditivos = []

    def add(self, dimensao, fator, pontos, fonte, detalhe="", criterio="cnpj", impeditivo=False):
        peso = FORCA_EVIDENCIA.get(criterio, 0.5)
        efetivo = round(pontos * peso, 1)
        self.fatores.append({
            "dimensao": dimensao, "dimensao_nome": DIMENSOES[dimensao], "fator": fator,
            "pontos_base": pontos, "forca_evidencia": peso, "pontos": efetivo,
            "fonte": fonte, "detalhe": detalhe, "criterio": criterio,
        })
        # Impeditivo só vale com evidência forte (CNPJ / CPF mascarado / nome+idade).
        if impeditivo and peso >= 0.7:
            self.impeditivos.append(f"{fator} ({fonte})")


def avaliar(dados: dict) -> dict:
    """`dados` = retorno de dataset_queries.obter_empresa."""
    a = _Avaliacao()
    emp = dados.get("empresa") or {}
    capital = float(emp.get("capital_social") or 0)

    # ---------------------------------------------------------- listas
    for s in dados.get("sancoes_administrativas") or []:
        tipo = (s.get("tipo") or "").upper()
        vig = _vigente(s.get("data_fim"))
        via_socio = bool(s.get("nome_socio_vinculado"))
        crit = "socio" if via_socio else "direto"
        fator_tempo = 1.0 if vig else 0.3
        quem = f" — via sócio {s['nome_socio_vinculado']}" if via_socio else ""
        status = "vigente" if vig else "encerrada"
        if tipo == "TRABALHO_ESCRAVO":
            a.add("listas", "Lista Suja do trabalho escravo", 50, "MTE", f"{status}{quem}", crit, impeditivo=not via_socio)
        elif tipo in ("CEIS", "CNEP"):
            a.add("listas", f"Empresa no {tipo}", 40 * fator_tempo, "CGU",
                  f"{s.get('motivo') or s.get('fundamentacao') or ''} ({status}){quem}"[:200], crit,
                  impeditivo=vig and not via_socio)
        elif tipo == "CEPIM":
            a.add("listas", "Impedida de receber recursos federais (CEPIM)", 20 * fator_tempo, "CGU", f"{status}{quem}", crit)
        elif "LENI" in tipo:
            a.add("listas", "Acordo de leniência (admissão de ato lesivo)", 20, "CGU", status, crit)
        elif "TCEES" in tipo:
            a.add("listas", f"Sanção do TCEES ({s.get('tipo')})", 25 * fator_tempo, "TCEES", f"{status}{quem}", crit,
                  impeditivo=vig and not via_socio and "INID" in tipo)
        else:
            a.add("listas", f"Sanção administrativa ({s.get('tipo')})", 15 * fator_tempo, "CGU", f"{status}{quem}", crit)

    socios_ocorr = dados.get("ocorrencias_socios") or []
    for o in socios_ocorr:
        f, crit = o.get("fonte"), o.get("criterio") or "nome_completo"
        quem = o.get("nome_socio_vinculado") or "a própria empresa"
        if f in ("OFAC", "ONU", "UK_SANCOES"):
            a.add("listas", f"Lista de sanções internacional ({f.replace('_', ' ')})", 50,
                  o.get("orgao") or f, f"{quem}: {o.get('descricao') or ''}"[:200], crit, impeditivo=True)

    # ---------------------------------------------------------- fiscal
    dividas = dados.get("dividas_ativas") or []
    if dividas:
        total = sum(float(d.get("valor") or 0) for d in dividas)
        ajuizada = any((d.get("ajuizada") or "").upper() == "SIM" for d in dividas)
        pts = 8
        det = f"{len(dividas)} inscrição(ões), {_brl(total)}"
        if total >= 1_000_000:
            pts += 7
        elif total >= 100_000:
            pts += 4
        if capital > 0 and total > capital:
            pts += 5
            det += " — maior que o capital social"
        if ajuizada:
            pts += 5
            det += " — com execução fiscal ajuizada"
        a.add("fiscal", "Dívida ativa da União", pts, "PGFN", det)
    pf = [o for o in socios_ocorr if o.get("fonte") == "PGFN_PF"]
    if pf:
        a.add("fiscal", "Sócio com dívida ativa da União em nome próprio", min(8, 4 + 2 * (len(pf) - 1)),
              "PGFN", ", ".join(o.get("nome_socio_vinculado") or "" for o in pf)[:200], "cpf_mascarado+nome")

    # ---------------------------------------------------------- judicial
    resumo = dados.get("resumo") or {}
    n_reu = int(resumo.get("qtd_processos_re") or 0)
    if n_reu:
        # escala log: 1 → 4, 10 → 8, 100 → 12 (empresa grande litiga muito; não explode)
        pts = min(12, 4 + 4 * math.log10(n_reu))
        a.add("judicial", "Ré em processos judiciais", round(pts, 1), "DJEN/CNJ",
              f"{n_reu}{'+' if n_reu >= 100 else ''} processo(s) como ré", "razao_social")
    proc = dados.get("processos_judiciais") or []
    criminais = [p for p in proc if p.get("polo") == "Réu" and any(t in (p.get("classe") or "").upper()
                 for t in ("PENAL", "CRIMINAL"))]
    improb = [p for p in proc if p.get("polo") == "Réu" and "IMPROBIDADE" in (p.get("classe") or "").upper()]
    if improb:
        a.add("judicial", "Ré em ação de improbidade administrativa", 10, "DJEN/CNJ",
              f"{len(improb)} processo(s)", "razao_social")
    if criminais:
        a.add("judicial", "Parte ré em processo criminal", 6, "DJEN/CNJ", f"{len(criminais)} processo(s)", "razao_social")
    if resumo.get("qtd_processos_socios_es"):
        a.add("judicial", "Sócio com processos pessoais em tribunais do ES", 3, "DJEN/CNJ",
              f"{resumo['qtd_processos_socios_es']} processo(s)", "nome_completo")

    # ---------------------------------------------------------- ambiental
    infr = dados.get("infracoes_ambientais") or []
    if infr:
        valor = sum(float(i.get("valor_multa") or i.get("valor") or 0) for i in infr)
        pts = 8 + (5 if valor >= 100_000 else 0) + (4 if any((i.get("gravidade") or "") == "Grave" for i in infr) else 0)
        a.add("ambiental", "Infrações ambientais (IBAMA)", pts, "IBAMA",
              f"{len(infr)} auto(s), {_brl(valor)} em multas")
    for o in socios_ocorr:
        if o.get("fonte") == "IBAMA_EMBARGO":
            vig = "vigente" in (o.get("situacao") or "")
            if o.get("criterio") == "cnpj":
                a.add("ambiental", "Área embargada pelo IBAMA (empresa)", 12 if vig else 4, "IBAMA",
                      o.get("situacao") or "", "cnpj")
            else:
                a.add("ambiental", "Sócio com área embargada pelo IBAMA", 4 if vig else 1, "IBAMA",
                      f"{o.get('nome_socio_vinculado')}: {o.get('situacao') or ''}", o.get("criterio"))

    # ---------------------------------------------------------- risco-país (GAFI, Rec. 19)
    # País do sócio estrangeiro como registrado na Receita (base nacional de sócios).
    vistos_pais = set()
    for r in dados.get("risco_pais_socios") or []:
        if not r.get("gafi") or (r.get("iso3"), r.get("gafi")) in vistos_pais:
            continue
        if r.get("pais_confirmado") == 0:
            continue  # código de país sabidamente trocado no cadastro (ex.: 187 x 190, Coreias)
        vistos_pais.add((r.get("iso3"), r.get("gafi")))
        quem = f"{r.get('nome_socio') or 'sócio'} ({r.get('pais_nome')}, segundo o cadastro da Receita)"
        if r["gafi"] == "acao":
            a.add("listas", "Sócio de jurisdição sob chamado à ação do GAFI (lista negra)", 25, "GAFI/FATF",
                  quem, "direto")
        else:
            a.add("exposicao", "Sócio de jurisdição sob monitoramento reforçado do GAFI (lista cinza)", 6,
                  "GAFI/FATF", quem, "direto")

    # ---------------------------------------------------------- exposição
    vinc = dados.get("vinculos_politicos") or []
    pep = [v for v in vinc if (v.get("fonte") or "") == "PEP"]
    if pep:
        a.add("exposicao", "Sócio pessoa exposta politicamente (PEP)", 8, "CGU",
              ", ".join(sorted({v.get("nome_socio_vinculado") or "" for v in pep}))[:200], "cpf_mascarado+nome")
    if any((v.get("fonte") or "").startswith("TSE_CANDIDATURA") for v in vinc):
        a.add("exposicao", "Sócio candidato a cargo eletivo", 3, "TSE", "", "cpf_mascarado+nome")
    tem_contrato_publico = bool(dados.get("contratos_pncp") or dados.get("contratos_governamentais"))
    if tem_contrato_publico and any((v.get("fonte") or "").startswith("TSE_DOACAO") for v in vinc):
        a.add("exposicao", "Doação eleitoral de sócio + contratos com o poder público", 6, "TSE/PNCP",
              "combinação que pede verificação de conflito de interesse", "cpf_mascarado+nome")
    pesos_socio = {
        "CEAF": (10, "Sócio expulso da administração pública federal"),
        "BCB_INABILITADO": (10, "Sócio inabilitado pelo Banco Central"),
        "TCU_INABILITADO": (10, "Sócio inabilitado pelo TCU para cargo público"),
        "CVM_SANCIONADOR": (6, "Sócio acusado em processo sancionador da CVM"),
        "SERVIDOR_FEDERAL": (3, "Sócio servidor público federal"),
    }
    vistos = set()
    for o in socios_ocorr:
        f = o.get("fonte")
        if f in pesos_socio and (f, o.get("nome_socio_vinculado")) not in vistos:
            vistos.add((f, o.get("nome_socio_vinculado")))
            pts, nome = pesos_socio[f]
            if f == "SERVIDOR_FEDERAL" and tem_contrato_publico:
                pts, nome = 8, "Sócio servidor público federal + contratos com o poder público"
            a.add("exposicao", nome, pts, o.get("orgao") or f,
                  f"{o.get('nome_socio_vinculado') or 'empresa'}: {o.get('descricao') or ''}"[:200],
                  o.get("criterio") or "nome_completo")

    # ---------------------------------------------------------- fachada
    for o in socios_ocorr:
        f = o.get("fonte")
        if f == "BOLSA_FAMILIA":
            pts = 8 + (7 if capital >= 100_000 else 0) + (5 if tem_contrato_publico else 0)
            det = f"{o.get('nome_socio_vinculado')}"
            if capital >= 100_000:
                det += f" — capital social de {_brl(capital)}"
            if tem_contrato_publico:
                det += " — empresa com contratos públicos"
            a.add("fachada", "Sócio favorecido de programa social (sinal de interposição)", pts, "MDS/CGU", det,
                  o.get("criterio") or "cpf_mascarado+nome")
        elif f == "ICIJ_OFFSHORE":
            a.add("fachada", "Ligação com offshore (Offshore Leaks)", 6, "ICIJ",
                  f"{o.get('nome_socio_vinculado') or 'empresa'}: {o.get('descricao') or ''}"[:200],
                  o.get("criterio") or "nome_completo")
    valor_pub = float(resumo.get("valor_total_contratos_pncp") or 0) + float(resumo.get("valor_total_contratos_governamentais") or 0)
    if valor_pub >= 1_000_000 and 0 < capital < valor_pub / 100:
        a.add("fachada", "Capital social muito baixo frente aos contratos públicos", 6, "Receita/PNCP",
              f"capital {_brl(capital)} × contratos {_brl(valor_pub)}")

    # ---------------------------------------------------------- consolidação
    por_dim = {}
    for f in a.fatores:
        por_dim[f["dimensao"]] = por_dim.get(f["dimensao"], 0) + f["pontos"]
    dimensoes = [{"dimensao": k, "nome": DIMENSOES[k], "pontos": round(min(v, TETO_DIMENSAO[k]), 1),
                  "teto": TETO_DIMENSAO[k]} for k, v in por_dim.items()]
    nota = min(100.0, sum(d["pontos"] for d in dimensoes))
    if a.impeditivos:
        nota = max(nota, 60.0)
    nota = round(nota)
    nivel, diligencia = next((n, d) for minimo, n, d in NIVEIS if nota >= minimo)
    return {
        "nota": nota,
        "nivel": nivel,
        "diligencia_recomendada": diligencia,
        "impeditivos": a.impeditivos,
        "dimensoes": sorted(dimensoes, key=lambda d: -d["pontos"]),
        "fatores": sorted(a.fatores, key=lambda f: -f["pontos"]),
        "versao": VERSAO,
        "metodologia": (
            "Nota de risco de integridade de 0 a 100 (maior = mais risco), por regras explícitas. "
            "Fatores e níveis seguem a abordagem baseada em risco do GAFI/FATF (Rec. 1, 10, 12, 19 e 24), "
            "a diligência de terceiros do Decreto 11.129/2022 (art. 57, XIII), as diretrizes de integridade "
            "da CGU e os níveis de diligência da Circular BCB 3.978/2020. Os pesos são calibração deste "
            "projeto; cada ponto é multiplicado pela força da evidência do cruzamento e sanções encerradas "
            "pesam menos. Apontamento em lista internacional ou sanção vigente por CNPJ eleva a nota a no "
            "mínimo 60 (Crítico). Não é juízo de culpa: indica o nível de verificação recomendado."
        ),
    }
