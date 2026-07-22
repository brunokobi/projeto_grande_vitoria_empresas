# CLAUDE.md — Contexto do projeto para o Claude Code

Este arquivo é carregado automaticamente pelo Claude Code. Ele resume o
estado do projeto, as decisões tomadas e as **armadilhas já descobertas e
corrigidas** — para não repetir investigação em outra máquina.

## O que é

Pipeline ETL em Python que constrói um **dataset de empresas ativas da
Grande Vitória (ES)** — Vitória, Vila Velha, Serra, Cariacica, Viana,
Guarapari, Fundão — cruzando fontes públicas: base cadastral (Receita
Federal), JUCEES, sanções federais (CEIS/CNEP) e estaduais (TCEES), dívida
ativa (PGFN), infrações ambientais (IBAMA), processos judiciais (DataJud/CNJ)
e geocodificação (OpenStreetMap/Nominatim). Objetivo de uso: **prospecção
de clientes**.

## Como rodar

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # ajuste o NOMINATIM_USER_AGENT com seu e-mail
set -a && source .env && set +a  # carrega o .env (zsh/bash)

python main.py --etapa cnpj      # 1º SEMPRE — define o universo de CNPJs
python main.py --etapa jucees
python main.py --etapa sancoes
python main.py --etapa tcees
python main.py --etapa ibama
python main.py --etapa datajud   # rate-limited, MUITO lento (dias)
python main.py --etapa geo       # rate-limited, lento (dias)
python main.py --etapa exportar  # gera output/*.csv e *.xlsx
```

## Estado atual (22/07/2026)

Rodado numa primeira máquina, base do mês **2026-07** da Receita:

| Etapa    | Resultado                                    | Status |
|----------|----------------------------------------------|--------|
| cnpj     | 344.130 empresas ativas                      | ✅ ok  |
| jucees   | 88.349 registros vinculados                  | ✅ ok  |
| sancoes  | 158.675 registros de dívida ativa (PGFN)     | ✅ ok  |
| tcees    | 17 sanções estaduais                         | ✅ ok  |
| ibama    | 1.326 infrações ambientais                   | ✅ ok  |
| datajud  | ~83/344.130 (pausado — retomável)            | ⏸️ parcial |
| geo      | ~1.776/344.130 (pausado — retomável)         | ⏸️ parcial |
| exportar | —                                            | ⏳ pendente |

Distribuição cnpj: Vila Velha 90.865, Serra 85.636, Vitória 78.872,
Cariacica 51.479, Guarapari 23.710, Viana 11.038, Fundão 2.530.

**datajud e geo são retomáveis** via `data/checkpoints/*.json` — reexecutar
a etapa continua de onde parou. Para 344 mil empresas com rate limit externo
(1 req/s), essas duas etapas levam DIAS, não horas. Isso é do rate limit das
APIs públicas (CNJ, Nominatim), não do código.

## Armadilhas já descobertas e corrigidas (NÃO regredir)

1. **RFB migrou para Nextcloud.** A URL antiga de índice HTML
   (`arquivos.receitafederal.gov.br/dados/cnpj/...`) dá 404. Agora é uma
   instância Nextcloud; `cnpj_ingest.py` resolve o token de compartilhamento
   dinamicamente (segue o redirect da raiz) e lista/baixa via WebDAV
   (PROPFIND). Não usa mais BeautifulSoup.

2. **Coluna `municipio` da RFB é CÓDIGO, não nome.** O arquivo de
   Estabelecimentos traz um código interno da Receita (ex.: 5705=VITORIA),
   não o nome. É resolvido via `Municipios.csv` do mesmo mês. O filtro
   antigo (por nome) dava **zero** empresas. Corrigido em
   `resolver_municipios_alvo`. A coluna `municipio` no banco guarda o NOME
   (geo_enrich depende disso).

3. **IBAMA é UTF-8; RFB/PGFN são latin-1.** Ler o IBAMA como latin-1
   corrompe acentos (`InfraÃ§Ã£o`). Corrigido para `encoding="utf-8"`.

4. **PGFN e IBAMA vêm como ZIP com vários CSVs**, não CSV único. Ambos os
   módulos extraem o zip antes de processar. A PGFN tem checkpoint por
   arquivo (6 CSVs, ~8,4 GB) — se cair no meio, não reprocessa.

5. **Bug do valor da dívida ativa.** Usava `normalizar_cnpj` (só dígitos)
   para o valor monetário, destruindo o número. Corrigido com `_to_float`
   (formato BR). A coluna de situação real é `SITUACAO_INSCRICAO`, não
   `SITUACAO`.

6. **DATAJUD_API_KEY vazia no .env.** `os.environ.get(k, default)` NÃO usa o
   default quando a var existe mas está vazia (`source .env` a define como
   ""). Corrigido para `os.environ.get(k) or FALLBACK` em config.py.

7. **`.env` sem aspas quebra o `source`.** O `NOMINATIM_USER_AGENT` tem
   parênteses — precisa estar entre aspas.

8. **Download atômico.** Downloads grandes da RFB caem por timeout. Baixa
   para `.parcial` e só renomeia ao concluir + retry, para não deixar
   arquivo parcial sendo tratado como "já baixado".

## Regras operacionais

- **LGPD:** o banco/output contêm dados pessoais (nome/CPF mascarado de
  sócios, endereços). **Nunca** commitar `data/` nem `output/` — estão no
  `.gitignore`. Repositório é público: só código sobe.
- Ao debugar uma etapa que falha, investigar a causa real (ler o traceback,
  inspecionar o dado/API de verdade), corrigir e reexecutar — as etapas são
  idempotentes/retomáveis.
- `data/raw/` chega a ~10 GB. Depois que cnpj+jucees gravam no banco, os
  zips/CSVs extraídos podem ser apagados para liberar espaço.

## Roadmap (ainda não implementado)

- **Servidor MCP** expondo o dataset como ferramentas (buscar por
  CNAE/município/pendências, obter por CNPJ).
- **API REST (FastAPI)** para consulta externa.
- Ambos consultam o SQLite em `data/grande_vitoria.db`.

## Continuar em outra máquina

O banco `data/grande_vitoria.db` (~139 MB) **não** está no git (limite do
GitHub + LGPD). Para continuar datajud/geo sem refazer o `cnpj` (que leva
horas + 10 GB de download), transfira o `.db` e `data/checkpoints/` por fora
(nuvem/USB). Sem eles, rode `python main.py --etapa cnpj` primeiro para
reconstruir a base, depois retome datajud/geo.
