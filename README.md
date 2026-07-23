<div align="center">

# 🗺️ Dataset de Empresas da Grande Vitória (ES)

### A base aberta mais completa de empresas ativas do Espírito Santo — pronta para prospecção, pesquisa e análise de mercado.

Mais de **344 mil empresas ativas** de **7 municípios**, cruzando dados cadastrais, jurídicos, sanções, dívida ativa, infrações ambientais e enriquecimento geográfico — tudo a partir de **fontes públicas oficiais**. Consulte por um **dashboard web**, uma **API REST** ou direto no **Claude** (MCP).

<br>

[![Empresas](https://img.shields.io/badge/empresas%20ativas-344k%2B-2563eb?style=flat-square)](#)
[![Municípios](https://img.shields.io/badge/munic%C3%ADpios-7-16a34a?style=flat-square)](#)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=flat-square&logo=python&logoColor=white)](#)
[![API](https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](#-consumir-o-dataset)
[![MCP](https://img.shields.io/badge/MCP-compat%C3%ADvel-8A2BE2?style=flat-square)](#-consumir-o-dataset)
[![Status](https://img.shields.io/badge/status-%F0%9F%9A%A7%20em%20constru%C3%A7%C3%A3o-f59e0b?style=flat-square)](#-projeto-em-construção)

<br>

<a href="https://github.com/sponsors/brunokobi">
  <img src="https://img.shields.io/badge/%E2%9D%A4%EF%B8%8F%20Apoiar%20este%20projeto-GitHub%20Sponsors-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Apoiar este projeto no GitHub Sponsors" height="42">
</a>

<sub>Projeto aberto e sem fins lucrativos — seu apoio custeia a atualização mensal das bases.</sub>

</div>

---

## ⚡ Começar em 1 comando

O dataset é distribuído como **GitHub Release** (não fica versionado no repo — mantém tudo leve). O `setup.sh` cria o ambiente, instala as dependências e **baixa o dataset** automaticamente:

```bash
git clone https://github.com/brunokobi/projeto_grande_vitoria_empresas.git
cd projeto_grande_vitoria_empresas
bash setup.sh
source .venv/bin/activate
uvicorn api:app        # abre em http://localhost:8000
```

Pronto: **dashboard** em `http://localhost:8000`, **API** em `/docs`, e o **MCP** já detectado pelo Claude Code (`.mcp.json`).

> **Nota (LGPD).** Os dados vêm de fontes públicas oficiais, mas o dataset consolida dados de pessoas (nome/CPF mascarado de sócios, endereços). Use de forma responsável e conforme a LGPD.

---

## 🚧 Projeto em construção

Em desenvolvimento ativo — estrutura e dados ainda podem mudar. Estado atual:

| Componente | Status |
|---|---|
| Base cadastral, JUCEES, dívida ativa (PGFN), sanções (TCEES), infrações (IBAMA) | ✅ prontos |
| Geocodificação (OpenStreetMap) · Processos judiciais (DataJud/CNJ) | 🚧 em processamento (rate limit) |
| Contato & redes sociais (WhatsApp, site, Instagram…) | 🧪 implementado |
| Dashboard · API REST · MCP · export Excel/PDF | ✅ funcionais |

---

## 💼 O que você recebe

| | |
|---|---|
| 🏢 **Cobertura** | +344 mil empresas ativas de Vitória, Vila Velha, Serra, Cariacica, Viana, Guarapari e Fundão |
| 📇 **Dados cadastrais** | CNPJ, razão social, CNAE (por nome), porte, regime tributário, capital, endereço, sócios |
| ⚖️ **Situação jurídica/fiscal** | Processos (DataJud/CNJ), sanções federais/estaduais, dívida ativa, infrações ambientais |
| 🧭 **Enriquecimento** | Geocodificação (mapa) e contato/redes sociais |
| 🚩 **Triagem rápida** | Sinalização de pendência jurídico-fiscal para filtrar em segundos |
| 🔌 **Acesso** | Dashboard web, API REST (FastAPI), servidor MCP (Claude), export Excel e PDF |

---

## 🔗 Fontes de dados cruzadas

Tudo montado **exclusivamente a partir de fontes públicas oficiais**, cruzadas pelo **CNPJ**:

**Receita Federal** (cadastro/sócios) · **JUCEES** (registro comercial) · **PGFN** (dívida ativa) · **TCEES** (sanções estaduais) · **IBAMA** (infrações ambientais) · **DataJud/CNJ** (processos) · **OpenStreetMap** (geolocalização).

> A construção/atualização do dataset é feita por um pipeline de extração mantido em repositório separado. Este repositório é o **produto de consumo** (dataset + ferramentas).

---

## 🖥️ Consumir o dataset

A lógica de consulta é compartilhada (`src/dataset_queries.py`) entre o dashboard, a API e o MCP — todos leem o SQLite em modo **somente-leitura**.

### Dashboard web
`uvicorn api:app` → **http://localhost:8000**. Filtros de prospecção (segmento CNAE, município, porte, regime, pendência, capital, contato/redes, busca), visão 360º por empresa com mapa, e **export Excel/PDF** da lista filtrada.

### API REST (FastAPI)
- `GET /estatisticas` — panorama do dataset
- `GET /segmentos` — segmentos (divisões CNAE) com contagem
- `GET /empresas` — busca com filtros (`municipio`, `cnae_prefix`, `porte`, `regime_tributario`, `texto`, `tem_pendencia`, `com_telefone`, `com_email`, `com_whatsapp`, `com_rede_social`, `capital_min/max`, `ordenar_por`, `limite`, `offset`)
- `GET /empresas/{cnpj}` — visão 360º
- `GET /export/empresas.xlsx` · `GET /export/empresas.pdf` — lista filtrada
- Docs interativas em `/docs`

### Servidor MCP
Ferramentas `estatisticas`, `buscar_empresas`, `obter_empresa` para o Claude e outros clientes MCP. O `.mcp.json` faz o Claude Code detectar automaticamente após o `setup.sh`.

---

## 💛 Apoie o projeto

Projeto aberto; seu apoio custeia a atualização mensal das bases e a manutenção.

**→ [github.com/sponsors/brunokobi](https://github.com/sponsors/brunokobi)** · níveis em [SPONSORS.md](SPONSORS.md)

---

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
