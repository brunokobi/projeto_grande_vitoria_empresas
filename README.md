<div align="center">

# 🗺️ Dataset de Empresas da Grande Vitória (ES)

### A base aberta mais completa de empresas ativas do Espírito Santo — pronta para prospecção, pesquisa e análise de mercado.

**344 mil empresas ativas** de **7 municípios**, cruzando dados cadastrais, **sócios**, jurídicos, sanções, dívida ativa e infrações ambientais — tudo de **fontes públicas oficiais**. Com **dashboard**, **API REST**, **MCP** (Claude) e **classificação de leads**.

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

<sub>Projeto aberto e sem fins lucrativos — seu apoio custeia a atualização mensal das bases.</sub>

</div>

---

## ⚡ Começar em 1 comando

O dataset é distribuído como **GitHub Release** (não fica versionado no repo — mantém tudo leve). O `setup.sh` cria o ambiente, instala dependências e **baixa o dataset**:

```bash
git clone https://github.com/brunokobi/projeto_grande_vitoria_empresas.git
cd projeto_grande_vitoria_empresas
bash setup.sh
source .venv/bin/activate
uvicorn api:app        # http://localhost:8000
```

Pronto: **dashboard** em `http://localhost:8000`, **API** em `/docs`, e o **MCP** detectado pelo Claude Code (`.mcp.json`).

> **Nota (LGPD).** Os dados vêm de fontes públicas oficiais, mas o dataset consolida dados de pessoas (nomes de sócios, CPF mascarado, endereços). Use de forma responsável e conforme a LGPD.

---

## 🚧 Projeto em construção

Em desenvolvimento ativo. Estado atual:

| Componente | Status |
|---|---|
| Cadastro (Receita) · **Sócios** · JUCEES | ✅ pronto (344k empresas · 231k sócios) |
| Dívida ativa PGFN (detalhada) · Sanções federais **CEIS/CNEP** + estaduais **TCEES** · Infrações **IBAMA** (detalhadas) | ✅ pronto |
| Geocodificação (mapa) · Processos judiciais (DataJud/CNJ) | 🚧 em processamento (rate limit — dias) |
| Contato & redes sociais (WhatsApp, site, Instagram…) | 🧪 implementado |
| Dashboard · API · MCP · export Excel/PDF · **classificação de leads** | ✅ funcionais |

---

## 💼 O que você recebe

| | |
|---|---|
| 🏢 **Cadastro** | CNPJ, razão social, CNAE (por nome), porte, regime, capital, endereço, situação |
| 👥 **Sócios + rede** | Quadro societário (nome, qualificação, faixa etária) e **em quais outras empresas o mesmo sócio aparece** |
| ⚖️ **Situação jurídico-fiscal detalhada** | Dívida ativa (tipo de tributo, ajuizamento, risco), sanções federais/estaduais (fundamentação), infrações IBAMA (valor, gravidade), processos |
| 🧭 **Enriquecimento** | Geolocalização (mapa) e contato/redes sociais |
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
| **CGU** — Portal da Transparência | Sanções federais **CEIS/CNEP** (fundamentação legal) | ✅ |
| **TCEES** | Sanções estaduais (processo/deliberação) | ✅ |
| **IBAMA** | Infrações ambientais (valor da multa, gravidade, situação) | ✅ |
| **OpenStreetMap** | Geolocalização (latitude/longitude) | 🚧 |
| **DataJud / CNJ** | Processos judiciais (TJES) | 🚧 |
| IEMA-ES · RAIS/CAGED | Ambiental estadual · nº de empregados | 🔭 planejado |

> A construção/atualização do dataset é feita por um pipeline de extração mantido em repositório separado. Este é o **produto de consumo**.

---

## 🖥️ Consumir o dataset

Lógica de consulta compartilhada (`src/dataset_queries.py`) entre dashboard, API e MCP — todos leem o SQLite em **somente-leitura**.

### Dashboard web
`uvicorn api:app` → **http://localhost:8000**. Filtros (segmento CNAE, município, porte, regime, tipo de pendência, capital, contato/redes, busca), **visão 360º** por empresa com **cards expansíveis** (dívida, sanção, infração e sócios detalhados) + mapa, **classificação de leads** (questionário) e **export Excel/PDF**.

### API REST (FastAPI) — docs em `/docs`
- `GET /estatisticas` · `GET /segmentos`
- `GET /empresas` — busca com filtros (município, `cnae_prefix`, porte, regime, `tem_pendencia`, `com_processos`/`com_sancoes`/`com_ambiental`/`com_divida`, `com_telefone`/`com_email`/`com_whatsapp`/`com_rede_social`, capital, ordenação, paginação)
- `GET /empresas/{cnpj}` — visão 360º (cadastro, sócios+rede, pendências detalhadas, geo)
- `GET /classificar` — pontua e ranqueia leads por objetivo comercial
- `GET /export/empresas.xlsx` · `GET /export/empresas.pdf`

### Servidor MCP
Ferramentas `estatisticas`, `buscar_empresas`, `obter_empresa`, `classificar_empresas` para o Claude e outros clientes MCP. O `.mcp.json` é detectado automaticamente após o `setup.sh`.

---

## 💛 Apoie o projeto

**→ [github.com/sponsors/brunokobi](https://github.com/sponsors/brunokobi)** · níveis em [SPONSORS.md](SPONSORS.md)

## 💬 Contato, sugestões e contribuições

| Quero... | Como |
|---|---|
| 🔗 Sugerir nova fonte de dados | [Abrir issue →](https://github.com/brunokobi/projeto_grande_vitoria_empresas/issues/new?template=nova-fonte.yml) |
| 💡 Sugestão, melhoria ou pedido | [Abrir issue →](https://github.com/brunokobi/projeto_grande_vitoria_empresas/issues/new?template=sugestao.yml) |
| 🐞 Problema ou reclamação | [Abrir issue →](https://github.com/brunokobi/projeto_grande_vitoria_empresas/issues/new?template=problema.yml) |
| 📧 Falar direto | [brunokobi2@hotmail.com](mailto:brunokobi2@hotmail.com) |
| 🌐 Site / portfólio | [brunokobi.netlify.app](https://brunokobi.netlify.app) |

---

<div align="center">
<sub>Feito com 💛 no Espírito Santo · Dados de fontes públicas oficiais · Use conforme a LGPD</sub>
</div>
