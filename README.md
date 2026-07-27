<div align="center">

# 🗺️ Dataset de Empresas da Grande Vitória (ES)

### A base aberta mais completa de empresas ativas do Espírito Santo — pronta para prospecção, pesquisa e análise de mercado.

**344 mil empresas ativas** de **7 municípios**, cruzando dados cadastrais, **sócios**, jurídicos, sanções, dívida ativa, infrações ambientais e **flags de risco** (trabalho escravo, CEPIM, leniência) — tudo de **fontes públicas oficiais**. Com **mapa interativo**, **dashboard**, **API REST**, **MCP** (Claude) e **classificação de leads**.

<br>

[![Empresas](https://img.shields.io/badge/empresas%20ativas-344k%2B-2563eb?style=flat-square)](#)
[![Sócios](https://img.shields.io/badge/s%C3%B3cios-231k%2B-2563eb?style=flat-square)](#)
[![Municípios](https://img.shields.io/badge/munic%C3%ADpios-7-16a34a?style=flat-square)](#)
[![API](https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](#-consumir-o-dataset)
[![MCP](https://img.shields.io/badge/MCP-compat%C3%ADvel-8A2BE2?style=flat-square)](#-consumir-o-dataset)
[![Status](https://img.shields.io/badge/status-%F0%9F%9A%A7%20em%20constru%C3%A7%C3%A3o-f59e0b?style=flat-square)](#-projeto-em-construção)

<br>

<a href="https://github.com/sponsors/brunokobi">
  <img src="https://img.shields.io/badge/%E2%9D%A4%EF%B8%8F%20Apoiar%20este%20projeto-GitHub%20Sponsors-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Apoiar no GitHub Sponsors" height="42">
</a>

<sub>Projeto aberto e sem fins lucrativos — seu apoio custeia o pipeline rodando 24/7 e o dataset atualizando sozinho a cada 2h.</sub>

<br><br>

### ⭐ Se este projeto te for útil, **deixe uma estrela** — leva 1 segundo, é de graça e ajuda demais a dar visibilidade ao trabalho!

</div>

---

## 🌐 Acesse online (sem instalar nada)

| | |
|---|---|
| 🖥️ **Dashboard** | **[empresas.brunokobi.duckdns.org](https://empresas.brunokobi.duckdns.org)** |
| 🔌 **API REST** | [empresas.brunokobi.duckdns.org/docs](https://empresas.brunokobi.duckdns.org/docs) |
| 🤖 **MCP** (Claude, Cursor, Windsurf, VS Code, Cline...) | `https://empresas.brunokobi.duckdns.org/mcp/` — instruções por cliente em **[MCP.md](MCP.md)** |

---

## ⚡ Começar em 1 comando

O dataset é distribuído como **GitHub Release** (não fica versionado no repo — mantém tudo leve). O script de setup usa o [uv](https://docs.astral.sh/uv/) para criar o ambiente com um Python 3.12 isolado (instalando o próprio uv se preciso), instalar dependências e **baixar o dataset** — **não precisa ter Python pré-instalado**, nem depende da versão que o sistema operacional já traz.

**Linux, macOS ou WSL:**

```bash
git clone https://github.com/brunokobi/projeto_grande_vitoria_empresas.git
cd projeto_grande_vitoria_empresas
bash setup.sh
source .venv/bin/activate
uvicorn api:app        # http://localhost:8000
```

**Windows (PowerShell nativo, sem precisar de WSL):**

```powershell
git clone https://github.com/brunokobi/projeto_grande_vitoria_empresas.git
cd projeto_grande_vitoria_empresas
powershell -ExecutionPolicy Bypass -File setup.ps1
.venv\Scripts\Activate.ps1
uvicorn api:app        # http://localhost:8000
```

Pronto: **dashboard** em `http://localhost:8000`, **API** em `/docs`, e o **MCP** detectado pelo Claude Code (`.mcp.json`).

> **Nota (LGPD).** Os dados vêm de fontes públicas oficiais, mas o dataset consolida dados de pessoas (nomes de sócios, CPF mascarado, endereços). Use de forma responsável e conforme a LGPD.

---

## 📸 Telas

<div align="center">

**Dashboard — lista, filtros e mapa interativo**

<img src="docs/dashboard.png" alt="Dashboard" width="100%">

**Visão 360º da empresa** — cadastro, sócios + rede, pendências detalhadas e mapa

<img src="docs/empresa-360.png" alt="Visão 360º da empresa" width="70%">

</div>

---

## 🚧 Projeto em construção

Em desenvolvimento ativo. Estado atual:

| Componente | Status |
|---|---|
| Cadastro (Receita) · **Sócios** · JUCEES | ✅ pronto (344k empresas · 231k sócios) |
| Dívida ativa **PGFN** (detalhada) | ✅ pronto |
| Sanções federais **CEIS/CNEP** + estaduais **TCEES** | ✅ pronto |
| Infrações **IBAMA** (detalhadas) | ✅ pronto |
| **CEPIM** (impedidas de verba federal) · **Acordos de Leniência** (CGU) | ✅ pronto |
| **Lista Suja do trabalho escravo** (MTE) | ✅ pronto |
| **Mapa interativo** (MapLibre) + **satélite** na visão 360º | ✅ pronto |
| Geocodificação (coordenadas de todas as empresas) | 🚧 rodando 24/7 na VPS — **previsão ~30/07/2026** |
| Processos judiciais (**DJEN/CNJ**, por nome da parte) | 🚧 rodando 24/7 na VPS (ver nota) |
| Contato & redes sociais (WhatsApp, site, Instagram…) | 🧪 implementado |
| Dashboard · API · MCP · export Excel/PDF | ✅ funcionais |
| **Classificação de leads** (via API/MCP) | ✅ funciona — 🚧 removida temporariamente da UI do dashboard |

> 🔄 **Atualização automática:** o pipeline de geocodificação e processos
> judiciais roda continuamente numa VPS, e o dataset publicado (Release) é
> atualizado **a cada 2 horas** — o dashboard/API baixam a versão nova sozinhos,
> sem precisar de reinstalação. O cadastro base (Receita Federal) segue seu
> próprio ritmo mensal, que é quando a RFB publica dados novos.
>
> ⏳ **Geocodificação** depende do OpenStreetMap (~1 req/s), por isso leva dias —
> o restante do dataset já está completo. No mapa, empresas ainda sem coordenada
> são localizadas **na hora pelo endereço**.
>
> ⚖️ **Processos judiciais:** a API pública do DataJud **não expõe as partes**
> (CPF/CNPJ), então é impossível achar processos por empresa por ela. Em vez disso
> usamos o **DJEN / Comunica API do CNJ** (busca por nome da parte) — cobre
> litígio recente (era do DJEN, ~2022+).

---

## 💼 O que você recebe

| | |
|---|---|
| 🏢 **Cadastro** | CNPJ, razão social, CNAE (por nome), porte, regime, capital, endereço, situação |
| 👥 **Sócios + rede** | Quadro societário (nome, qualificação, faixa etária) e **em quais outras empresas o mesmo sócio aparece** |
| ⚖️ **Situação jurídico-fiscal detalhada** | Dívida ativa (tipo de tributo, ajuizamento, risco), sanções federais/estaduais (fundamentação), infrações IBAMA (valor, gravidade), processos (DJEN) |
| 🚩 **Flags de risco** | **Lista Suja do trabalho escravo** (MTE), **CEPIM** (impedidas de verba federal), **acordos de leniência** — filtráveis |
| 🗺️ **Mapa interativo** | Mapa geral da Grande Vitória com todos os pontos (clique → empresa) e **satélite** na visão 360º; filtros recortam o mapa |
| 🧭 **Enriquecimento** | Geolocalização e contato/redes sociais |
| 🎯 **Classificação de leads** | Questionário por objetivo comercial → score 0–100 (🔥 Quente / 🙂 Morno / ❄️ Frio) |
| 🔌 **Acesso** | Dashboard web, API REST, servidor MCP (Claude), export Excel e PDF |

---

## 🔗 Fontes de dados cruzadas

Tudo cruzado pelo **CNPJ**, exclusivamente de **fontes públicas oficiais**:

| Fonte | O que agrega | Status |
|---|---|:--:|
| **Receita Federal** (CNPJ) | Cadastro, **sócios**, CNAE, porte, capital, endereço | ✅ |
| **JUCEES** (dados.es.gov.br) | NIRE, constituição, natureza jurídica | ✅ |
| **PGFN** | Dívida ativa (tipo de tributo, valor, ajuizamento) | ✅ |
| **CGU** — Portal da Transparência | Sanções **CEIS/CNEP**, **CEPIM**, **Acordos de Leniência** | ✅ |
| **TCEES** | Sanções estaduais (processo/deliberação) | ✅ |
| **IBAMA** | Infrações ambientais (valor da multa, gravidade, situação) | ✅ |
| **MTE** — Cadastro de Empregadores | **Lista Suja** do trabalho escravo | ✅ |
| **OpenStreetMap / Nominatim** | Geolocalização (mapa; fallback por endereço) | 🚧 |
| **DJEN / CNJ** (Comunica API) | Processos judiciais (por nome da parte) | 🚧 |
| IEMA-ES · RAIS/CAGED | Ambiental estadual · nº de empregados | 🔭 planejado |

> A construção/atualização do dataset é feita por um pipeline de extração mantido em repositório separado. Este é o **produto de consumo**.

---

## 🖥️ Consumir o dataset

Lógica de consulta compartilhada (`src/dataset_queries.py`) entre dashboard, API e MCP — todos leem o SQLite em **somente-leitura**.

### Dashboard web
`uvicorn api:app` → **http://localhost:8000**. **Mapa geral** da Grande Vitória (MapLibre GL) com todos os pontos geolocalizados — clique num ponto abre a empresa, e os filtros recortam o mapa. Filtros (segmento CNAE, município, porte, regime, tipo de pendência, **flags de risco**: trabalho escravo/CEPIM/leniência, capital, contato/redes, busca), **visão 360º** por empresa com **cards expansíveis** (processos, dívida, sanção, infração e sócios detalhados) + **mapa por satélite** e **export Excel/PDF**.

> A **classificação de leads** (questionário → score 0–100) segue disponível via API (`GET /classificar`) e MCP (`classificar_empresas`) — só foi tirada temporariamente da interface do dashboard.

### API REST (FastAPI) — docs em `/docs`
- `GET /estatisticas` · `GET /segmentos`
- `GET /empresas` — busca com filtros (município, `cnae_prefix`, porte, regime, `socio` (nome), `tem_pendencia`, `com_processos`/`com_sancoes`/`com_ambiental`/`com_divida`, `com_trabalho_escravo`/`com_cepim`/`com_leniencia`, `com_telefone`/`com_email`/`com_whatsapp`/`com_rede_social`, capital, ordenação, paginação)
- `GET /mapa` — pontos geolocalizados (lat/lng) com os mesmos filtros, para o mapa
- `GET /empresas/{cnpj}` — visão 360º (cadastro, sócios+rede, pendências detalhadas, geo)
- `GET /geocode` — resolve um endereço em lat/lng (fallback do mapa quando a empresa ainda não tem coordenada)
- `GET /classificar` — pontua e ranqueia leads por objetivo comercial
- `GET /export/empresas.xlsx` · `GET /export/empresas.pdf`

### Servidor MCP
Ferramentas `estatisticas`, `buscar_empresas`, `obter_empresa`, `classificar_empresas` para o Claude e outros clientes MCP. Duas formas de conectar: **remoto**, direto em `https://empresas.brunokobi.duckdns.org/mcp/` (sem instalar nada); ou **local**, via `.mcp.json` (detectado automaticamente pelo Claude Code após o `setup.sh`).

📘 **Tutorial completo de conexão** (Claude Desktop, Claude Code, Cursor, Windsurf, VS Code/Copilot, Cline): **[MCP.md](MCP.md)**.

---

## 💛 Apoie o projeto

[![GitHub Sponsors](https://img.shields.io/badge/❤%EF%B8%8F%20Apoiar-github.com%2Fsponsors%2Fbrunokobi-ea4aaa?style=flat-square&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/brunokobi) · níveis em [![SPONSORS.md](https://img.shields.io/badge/SPONSORS.md-24292e?style=flat-square&logo=markdown&logoColor=white)](SPONSORS.md)

## 💬 Contato, sugestões e contribuições

| Quero... | Como |
|---|---|
| 🔗 Sugerir nova fonte de dados | [![Abrir issue](https://img.shields.io/badge/Abrir%20issue-2563eb?style=flat-square&logo=github&logoColor=white)](https://github.com/brunokobi/projeto_grande_vitoria_empresas/issues/new?template=nova-fonte.yml) |
| 💡 Sugestão, melhoria ou pedido | [![Abrir issue](https://img.shields.io/badge/Abrir%20issue-2563eb?style=flat-square&logo=github&logoColor=white)](https://github.com/brunokobi/projeto_grande_vitoria_empresas/issues/new?template=sugestao.yml) |
| 🐞 Problema ou reclamação | [![Abrir issue](https://img.shields.io/badge/Abrir%20issue-2563eb?style=flat-square&logo=github&logoColor=white)](https://github.com/brunokobi/projeto_grande_vitoria_empresas/issues/new?template=problema.yml) |
| 📧 Falar direto | [![E-mail](https://img.shields.io/badge/brunokobi2@hotmail.com-EA4335?style=flat-square&logo=maildotru&logoColor=white)](mailto:brunokobi2@hotmail.com) |
| 🌐 Site / portfólio | [![Site](https://img.shields.io/badge/brunokobi.netlify.app-00C7B7?style=flat-square&logo=netlify&logoColor=white)](https://brunokobi.netlify.app) |

---

<div align="center">
<sub>Feito com 💛 no Espírito Santo · Dados de fontes públicas oficiais · Use conforme a LGPD</sub>
</div>
