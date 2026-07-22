<div align="center">

# 🗺️ Dataset de Empresas da Grande Vitória (ES)

### A base aberta mais completa de empresas ativas do Espírito Santo — pronta para prospecção, pesquisa e análise de mercado.

Mais de **344 mil empresas ativas** de **7 municípios**, cruzando dados cadastrais, jurídicos, sanções, dívida ativa, infrações ambientais e enriquecimento geográfico — tudo a partir de **fontes públicas oficiais**. Consulte via **API REST** ou direto no **Claude** (MCP).

<br>

[![Empresas](https://img.shields.io/badge/empresas%20ativas-344k%2B-2563eb?style=flat-square)](#)
[![Municípios](https://img.shields.io/badge/munic%C3%ADpios-7-16a34a?style=flat-square)](#)
[![Fontes públicas](https://img.shields.io/badge/fontes%20oficiais-6-64748b?style=flat-square)](#)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=flat-square&logo=python&logoColor=white)](#)
[![API](https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](#api-rest-fastapi)
[![MCP](https://img.shields.io/badge/MCP-compat%C3%ADvel-8A2BE2?style=flat-square)](#servidor-mcp)
[![Setup](https://img.shields.io/badge/setup-plug--and--play-f59e0b?style=flat-square)](#setup-r%C3%A1pido-plug-and-play)
[![Status](https://img.shields.io/badge/status-%F0%9F%9A%A7%20em%20constru%C3%A7%C3%A3o-f59e0b?style=flat-square)](#-projeto-em-construção)
[![Sponsor](https://img.shields.io/badge/apoie%20o%20projeto-%E2%9D%A4-ea4aaa?style=flat-square&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/brunokobi)

<br>

<a href="https://github.com/sponsors/brunokobi">
  <img src="https://img.shields.io/badge/%E2%9D%A4%EF%B8%8F%20Apoiar%20este%20projeto-GitHub%20Sponsors-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Apoiar este projeto no GitHub Sponsors" height="42">
</a>

<sub>Projeto aberto e sem fins lucrativos — seu apoio custeia a atualização mensal das bases.</sub>

</div>

---

## 🚧 Projeto em construção

Este repositório está em **desenvolvimento ativo** — estrutura, endpoints e dados ainda podem mudar. Estado atual:

| Componente | Status |
|---|---|
| Base cadastral (Receita Federal) | ✅ pronta — 344.130 empresas |
| JUCEES · Dívida ativa (PGFN) · Sanções (TCEES) · Infrações (IBAMA) | ✅ prontos |
| Processos judiciais (DataJud/CNJ) | 🚧 em processamento (rate limit — dias, retomável) |
| Geocodificação (OpenStreetMap) | 🚧 em processamento (rate limit — dias, retomável) |
| Contato & redes sociais (WhatsApp, site, Instagram…) | 🧪 implementado, ainda não rodado na base completa |
| Dashboard web · API REST · MCP · export Excel/PDF | ✅ funcionais (em ajuste de layout) |

> Contribuições, sugestões e apoio são bem-vindos enquanto o projeto amadurece. 💛

---

## 💼 O que você recebe

| | |
|---|---|
| 🏢 **Cobertura** | +344 mil empresas ativas de Vitória, Vila Velha, Serra, Cariacica, Viana, Guarapari e Fundão |
| 📇 **Dados cadastrais** | CNPJ, razão social, CNAE, porte, regime tributário, capital, endereço, sócios |
| ⚖️ **Situação jurídica/fiscal** | Processos (DataJud/CNJ), sanções federais e estaduais, dívida ativa, infrações ambientais |
| 🧭 **Enriquecimento** | Geocodificação (latitude/longitude) via OpenStreetMap |
| 🚩 **Triagem rápida** | Coluna `tem_pendencia_juridica_ou_fiscal` para filtrar em segundos |
| 🔌 **Acesso** | API REST (FastAPI), servidor MCP (Claude e afins), CSV e XLSX consolidados |

---

## 🔗 Fontes de dados cruzadas

Todo o dataset é montado **exclusivamente a partir de fontes públicas oficiais**, cruzadas pelo **CNPJ**. Abaixo, todas as fontes já integradas e as planejadas.

**Legenda:** ✅ integrada · 🚧 em processamento · ⚙️ opcional (requer configurar o link do arquivo) · 🔭 planejada (ainda não implementada)

| Fonte | Órgão / Portal | O que agrega ao dataset | Status |
|---|---|---|:--:|
| **Cadastro Nacional CNPJ** | Receita Federal — [dados abertos CNPJ](https://arquivos.receitafederal.gov.br/) | Razão social, nome fantasia, CNAE, porte, capital social, endereço, situação cadastral, **sócios**, opção Simples/MEI | ✅ |
| **Registro comercial (JUCEES)** | Junta Comercial do ES — [dados.es.gov.br](https://dados.es.gov.br/dataset/empresas) | NIRE, data de constituição, natureza jurídica | ✅ |
| **Dívida Ativa da União** | PGFN — [dadosabertos.pgfn.gov.br](https://dadosabertos.pgfn.gov.br/) | Inscrições em dívida ativa, valor consolidado, situação | ✅ |
| **Sanções estaduais** | TCEES — Tribunal de Contas do ES | Empresas inidôneas, proibidas de contratar, inabilitadas e com contas irregulares | ✅ |
| **Infrações ambientais** | IBAMA — [dados abertos](https://dadosabertos.ibama.gov.br/) | Autos de infração ambiental (federal) | ✅ |
| **Geocodificação** | OpenStreetMap / Nominatim | Latitude e longitude a partir do endereço | 🚧 |
| **Processos judiciais** | DataJud / CNJ — [API pública](https://datajud-wiki.cnj.jus.br/api-publica/) | Processos por CNPJ (TJES, TRT17, TRF2) | 🚧 |
| **Contato & redes sociais** | Derivado do próprio cadastro | Telefone → **WhatsApp**; e-mail → **site**; site → **Instagram/Facebook/LinkedIn** | 🧪 implementado |
| **Sanções federais** | CGU — Portal da Transparência ([CEIS](https://portaldatransparencia.gov.br/download-de-dados/ceis) / [CNEP](https://portaldatransparencia.gov.br/download-de-dados/cnep) / CEPIM) | Empresas inidôneas/suspensas e punidas na esfera federal | ⚙️ |
| **Ambiental estadual (IEMA-ES)** | IEMA — Instituto de Meio Ambiente do ES | Infrações ambientais estaduais | 🔭 |
| **Justiça estadual (TJES / e-SAJ)** | Tribunal de Justiça do ES | Processos estaduais direto na origem | 🔭 |
| **Vínculos de emprego (RAIS/CAGED)** | Ministério do Trabalho e Emprego | Nº de empregados por empresa (porte real) | 🔭 |

> As fontes marcadas com ⚙️ dependem de colar o link do arquivo do período desejado (ver `.env.example` / `config.py`); as 🔭 são extensões previstas para próximas versões.

---

## 💛 Apoie o projeto

Este é um projeto aberto que consolida dados públicos em um dataset útil para prospecção. Se ele te ajuda, considere apoiar — isso custeia o tempo de manutenção e a atualização periódica das bases (a Receita Federal publica dados novos todo mês):

<div align="center">
<a href="https://github.com/sponsors/brunokobi">
  <img src="https://img.shields.io/badge/%E2%9D%A4%EF%B8%8F%20Tornar--se%20apoiador-github.com%2Fsponsors%2Fbrunokobi-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Tornar-se apoiador" height="40">
</a>
</div>

Há níveis de apoio (mensal e único) com recompensas — veja [**SPONSORS.md**](SPONSORS.md). O botão **♥ Sponsor** no topo do repositório também leva pra lá.

---

## Setup rápido (plug-and-play)

O banco já consolidado vem versionado **comprimido** (`data/grande_vitoria.db.gz`, ~47 MB) junto com o progresso das etapas retomáveis (`data/checkpoints/`). Após clonar, um único comando prepara tudo:

```bash
bash setup.sh
```

Isso cria o `.venv`, instala as dependências, gera o `.env` a partir do modelo e descomprime o banco (~139 MB). Depois:

```bash
source .venv/bin/activate && set -a && source .env && set +a
python main.py --etapa datajud    # retoma de onde parou (via checkpoint)
python main.py --etapa geo         # idem
python main.py --etapa exportar    # gera output/ consolidado
```

> **Observação (LGPD).** Todos os dados vêm de fontes públicas oficiais (Receita Federal, PGFN, IBAMA, TCEES, DataJud/CNJ, JUCEES). Ainda assim, o dataset consolida dados de pessoas (nome/CPF mascarado de sócios, endereços). Use de forma responsável e conforme a LGPD. Os arquivos de dados descomprimidos (`data/*.db`, `data/raw/`, `output/`) **não** são versionados — só o banco comprimido entra no repositório.

---

## Consumir o dataset (Dashboard, MCP e API)

Além do CSV/XLSX da etapa `exportar`, o dataset pode ser consultado ao vivo — lê direto o SQLite consolidado, em modo **somente-leitura**. A lógica de consulta é compartilhada (`src/dataset_queries.py`) entre o dashboard, a API e o MCP.

### 🖥️ Dashboard web

Interface visual (tema verde-matrix) para explorar a base, servida pela própria API:

```bash
source .venv/bin/activate
uvicorn api:app          # abre o dashboard em http://localhost:8000
```

- **Filtros de prospecção**: segmento (divisão CNAE), município, porte, regime, situação jurídico-fiscal (com/sem pendência), capital, busca por nome e exigência de contato (telefone, e-mail, WhatsApp, rede social).
- **Visão 360º por empresa**: card destacado com cadastro, contato/redes, sócios, pendências (processos, sanções, dívida ativa, ambiental) e mapa.
- **Exportar** a lista filtrada em **Excel** e **PDF** (botões no topo).

### API REST (FastAPI)

```bash
source .venv/bin/activate
uvicorn api:app --reload      # http://localhost:8000
```

- `GET /estatisticas` — panorama do dataset (totais, por município/porte/CNAE)
- `GET /empresas` — busca com filtros: `municipio`, `cnae`, `porte`, `regime_tributario`, `texto`, `tem_pendencia`, `com_telefone`, `com_email`, `capital_min`, `capital_max`, `ordenar_por`, `limite`, `offset`
- `GET /empresas/{cnpj}` — visão 360º (cadastro, sócios, JUCEES, geo, pendências)
- Documentação interativa: `http://localhost:8000/docs`

### Servidor MCP

Expõe as mesmas consultas como ferramentas MCP (`estatisticas`, `buscar_empresas`, `obter_empresa`) para o Claude e outros clientes MCP. O repositório já traz um **`.mcp.json`** — o Claude Code detecta automaticamente ao abrir a pasta (após rodar o `setup.sh`). Para outros clientes (ex.: Claude Desktop), use caminhos absolutos:

```json
{
  "mcpServers": {
    "grande-vitoria-empresas": {
      "command": "/CAMINHO/ABSOLUTO/.venv/bin/python",
      "args": ["/CAMINHO/ABSOLUTO/mcp_server.py"]
    }
  }
}
```

---

## Estrutura

```
grande_vitoria_empresas/
├── config.py                  # configuração central (municípios, URLs, chaves)
├── main.py                    # orquestrador (CLI)
├── requirements.txt
├── database/
│   └── schema.sql             # schema SQLite
├── data/
│   ├── raw/                   # arquivos brutos baixados (zips, csvs)
│   └── checkpoints/           # progresso de etapas com rate limit
└── src/
    ├── db_utils.py            # conexão e upsert no SQLite
    ├── checkpoint.py          # retomada de processos longos
    ├── matching.py            # normalização de CNPJ e fuzzy match
    ├── cnpj_ingest.py         # ETAPA 1 — base cadastral (Receita Federal)
    ├── sanctions_ingest.py    # ETAPA 2 — CEIS/CNEP/dívida ativa (PGFN)
    ├── ibama_ingest.py        # ETAPA 3 — infrações ambientais (IBAMA)
    ├── datajud_client.py      # ETAPA 4 — processos judiciais (API DataJud/CNJ)
    └── places_enrich.py       # ETAPA 5 — geo/telefone/site (Google Places)
```

---

## Passo a passo para gerar o dataset

### 1. Preparar o ambiente

```bash
pip install -r requirements.txt
cp .env.example .env
```

Preencha o `.env` com:

- `DATAJUD_API_KEY` — **opcional**. Já vem com um valor padrão embutido em `config.py` (a chave pública vigente em 21/07/2026). Só preencha esta variável se a etapa `datajud` começar a dar erro 401/403 — sinal de que o CNJ trocou a chave — pegando a atualizada em https://datajud-wiki.cnj.jus.br/api-publica/acesso/. Quando isso acontece, o pipeline já para a etapa automaticamente com uma mensagem clara em vez de tentar todos os CNPJs e falhar silenciosamente.
- `GOOGLE_PLACES_API_KEY` — **removida**. A Places API do Google exige cartão cadastrado no Google Cloud mesmo dentro do free tier (pré-pagamento de R$50 reembolsável). Pra evitar essa dependência, o enriquecimento geográfico usa **OpenStreetMap/Nominatim** (etapa `geo`), gratuito e sem cartão. Trade-off: só traz latitude/longitude a partir do endereço — não traz telefone atualizado, site, avaliação nem horário de funcionamento (isso só o Google Places tem). `NOMINATIM_USER_AGENT` no `.env` é opcional, mas recomendado (identifica sua aplicação, exigido pela política de uso do servidor público do Nominatim).
- `JUCEES_DUMP_URL` — **opcional**. Já vem com o link estável do portal de dados abertos do ES embutido em `config.py` (baseado em resource_id do CKAN, não muda mensalmente como outras fontes). **Limitação importante**: esse dataset da JUCEES cobre só empresas com natureza jurídica "Sociedade Empresária" do ramo de serviços/comércio — não é o universo completo (não inclui MEI, Empresário Individual, etc.). É tratado como complemento à base da Receita (adiciona NIRE, data de constituição, natureza jurídica descritiva), não como substituto.
- `TCEES` (etapa `tcees`) — **sem configuração**. URLs estáveis embutidas em `config.py`. Traz sanções estaduais do Tribunal de Contas do ES (empresas inidôneas, proibidos de contratar, inabilitados, contas irregulares) que complementam o CEIS/CNEP federal — são gravadas na mesma tabela `sancoes_administrativas`, distinguidas pelo campo `tipo`, e já entram automaticamente na contagem e na flag de pendências do dataset final. Cada lista traz CPF ou CNPJ do responsável; só os CNPJs que batem com a base são vinculados (CPFs de pessoa física são ignorados, correto para um dataset de empresas).
- `CEIS_FILE_URL`, `CNEP_FILE_URL`, `PGFN_FILE_URL`, `IBAMA_FILE_URL` — cole a URL final do arquivo de cada fonte (não a página do dataset). Abra a página, clique no botão de exportação, copie o link do arquivo gerado. As páginas de referência estão comentadas em `config.py`.

Carregue as variáveis antes de rodar:

```bash
export $(cat .env | xargs)
```

### 2. Rodar o pipeline, etapa por etapa

A ordem importa — `cnpj` sempre primeiro, pois define o universo de CNPJs que todas as outras etapas usam como filtro:

```bash
python main.py --etapa cnpj        # base cadastral (pesado: pode levar horas)
python main.py --etapa jucees      # complemento JUCEES — NIRE, constituição, natureza jurídica
python main.py --etapa sancoes     # CEIS, CNEP, dívida ativa PGFN (federais)
python main.py --etapa tcees       # sanções estaduais do TCEES (inidôneas, proibidos de contratar, inabilitados, contas irregulares)
python main.py --etapa ibama       # infrações ambientais
python main.py --etapa datajud     # processos — sem --limite roda tudo (mais lento, respeita rate limit)
python main.py --etapa geo         # geocodificação via OpenStreetMap/Nominatim — todas as empresas (1 req/s, sem cartão)
python main.py --etapa exportar    # gera o dataset final consolidado
```

Ou tudo de uma vez (recomendado só depois de validar cada etapa isoladamente com uma amostra pequena, usando `--limite` nas etapas que aceitam):

```bash
python main.py --etapa tudo
```

### 3. Resultado final

Nota sobre a etapa `geo`: o Nominatim público limita a 1 requisição por segundo. Para uma base de dezenas de milhares de empresas, isso pode levar muitas horas — a etapa já imprime uma estimativa de tempo ao iniciar e é retomável via checkpoint (se cair no meio, rode de novo e ele continua de onde parou). Se precisar de mais velocidade, a alternativa dentro da política de uso do OpenStreetMap é subir uma instância própria do Nominatim via Docker (https://github.com/mediagis/nominatim-docker) e apontar `NOMINATIM_URL` no `.env` para o seu servidor local, sem rate limit externo.

Depois da etapa `exportar`, os arquivos ficam em `output/`:

- `empresas_grande_vitoria_consolidado.csv` — uma linha por empresa, com contagens agregadas (qtd. processos, sanções, infrações ambientais, dívida ativa) e uma coluna `tem_pendencia_juridica_ou_fiscal` pra triagem rápida.
- `empresas_grande_vitoria_dataset.xlsx` — mesmo consolidado na aba principal, mais uma aba de detalhe por categoria (sócios, processos, sanções, ambiental, dívida ativa).

---

## Variáveis de ambiente — referência completa

Ver `.env.example` para a lista completa e comentada.

---

## Pontos de atenção antes de rodar em produção

1. **Layouts de CSV mudam.** Os módulos `sanctions_ingest.py` e `ibama_ingest.py` foram escritos com base nos nomes de coluna documentados publicamente, mas o Portal da Transparência e o IBAMA já alteraram esses layouts no passado. Inspecione o cabeçalho do CSV baixado antes de rodar em produção e ajuste os nomes de coluna se necessário.

2. **URLs de download dinâmicas.** CEIS/CNEP/IBAMA geram links de exportação através de navegação na página (não é um link estático fixo). As URLs em `config.py` apontam para as páginas dos datasets — resolva a URL final do arquivo antes de rodar `sanctions_ingest.py` e `ibama_ingest.py` (ou automatize essa resolução com Selenium/Playwright se o botão de exportação depender de JavaScript).

3. **DataJud não tem "baixar tudo".** É uma API de busca — a única forma de cobrir todas as empresas é consultar uma por uma, por tribunal. Para milhares de CNPJs, isso é lento mesmo com rate limit baixo; rode em lotes com `--limite` e deixe rodando em background/cron.

4. **Matching sem CNPJ direto.** Quando uma fonte só traz razão social (não é o caso das fontes aqui, que trazem CNPJ, mas pode ocorrer em fontes adicionais como TJES/IEMA-ES), use `src/matching.py` — `match_fuzzy_por_razao_social`. Sempre revise uma amostra dos matches fuzzy manualmente; é o ponto mais frágil do pipeline (falso positivo associa registro à empresa errada).

5. **LGPD.** A tabela `socios` grava CPF já mascarado (como vem da Receita), mas mesmo assim é dado de pessoa física. Se o dataset for usado além de uso interno/prospecção, avalie anonimizar ainda mais ou remover essa tabela do dataset final.

6. **Situação cadastral.** O filtro em `cnpj_ingest.py` usa `situacao_cadastral == "02"` (código da Receita para ATIVA). Se quiser incluir empresas baixadas/suspensas para análise histórica, ajuste esse filtro.

---

## Extensões sugeridas (não implementadas)

- **IEMA-ES** (infrações ambientais estaduais) e **TJES/e-SAJ** direto: ambos geralmente exigem scraping de portal de consulta manual, sem API documentada — verificar termos de uso antes de automatizar.
- **RAIS/CAGED**: para número de empregados por empresa (proxy de porte real), como camada adicional de enriquecimento.

---

## 💬 Contato, sugestões e contribuições

Todo feedback é bem-vindo — sugerir uma **nova fonte de dados**, propor melhorias, pedir recursos ou reportar problemas. Escolha o canal:

| Quero... | Como |
|---|---|
| 🔗 **Sugerir nova fonte de dados** | [Abrir issue →](https://github.com/brunokobi/projeto_grande_vitoria_empresas/issues/new?template=nova-fonte.yml) |
| 💡 **Sugestão, melhoria ou pedido** | [Abrir issue →](https://github.com/brunokobi/projeto_grande_vitoria_empresas/issues/new?template=sugestao.yml) |
| 🐞 **Problema ou reclamação** | [Abrir issue →](https://github.com/brunokobi/projeto_grande_vitoria_empresas/issues/new?template=problema.yml) |
| 📧 **Falar direto / outros assuntos** | [brunokobi2@hotmail.com](mailto:brunokobi2@hotmail.com) |
| 🌐 **Site / portfólio** | [brunokobi.netlify.app](https://brunokobi.netlify.app) |

> As **issues** são públicas e permitem acompanhar o andamento do pedido. Não tem conta no GitHub? Manda um **e-mail** ou fale pelo [site](https://brunokobi.netlify.app). Toda sugestão de fonte entra na avaliação para as próximas versões (ver [Fontes de dados](#-fontes-de-dados-cruzadas)).

---

## Apoiadores

Quem apoia o projeto via [GitHub Sponsors](https://github.com/sponsors/brunokobi) aparece aqui. Detalhes dos níveis em [SPONSORS.md](SPONSORS.md).

### 🏢 Patrocinadores
_Seja o primeiro — [torne-se um patrocinador](https://github.com/sponsors/brunokobi)._

### 🚀 Apoiadores+
_Ainda não há apoiadores neste nível._

### ☕ Apoiadores
_Ainda não há apoiadores neste nível._

---

<div align="center">
<sub>Feito com 💛 no Espírito Santo · Dados de fontes públicas oficiais · Use conforme a LGPD</sub>

<br><br>

<a href="https://github.com/sponsors/brunokobi">
  <img src="https://img.shields.io/badge/%E2%9D%A4%EF%B8%8F%20Gostou%3F%20Apoie%20o%20projeto-GitHub%20Sponsors-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Apoie o projeto" height="40">
</a>
</div>
