# 🔌 Como conectar o dataset via MCP

Este projeto expõe um **servidor MCP** (Model Context Protocol) — ou seja, você
pergunta em linguagem natural na sua IA e ela consulta o dataset de empresas da
Grande Vitória direto, com estas ferramentas:

| Ferramenta | O que faz |
|---|---|
| `estatisticas` | Panorama geral (totais por município, porte e regime; registros e empresas por fonte; nota de integridade) |
| `buscar_empresas` | Busca com filtros (segmento, município, pendências, contato…) |
| `buscar_empresas_perto` | Busca num **raio (km)** de um ponto — endereço em texto livre ou lat/lon |
| `obter_empresa` | Visão 360º de um CNPJ (sócios+rede, dívidas, sanções, infrações, processos, vínculos políticos, contratos públicos, benefícios/renúncias fiscais, contexto ambiental e geológico) com resumo agregado |
| `classificar_empresas` | Pontua/ranqueia leads por objetivo comercial (score 0–100) |
| `ranking_doacoes_eleitorais` | Ranking de doações eleitorais (TSE) — candidatos que mais receberam e empresas que mais aparecem doando, por quantidade ou valor |
| `classes_processos` | Classes de processo judicial disponíveis (com contagem), pra refinar `com_processos` por `processo_classe` |
| `orgaos_sancionadores` | Órgãos sancionadores disponíveis (com contagem), pra refinar `com_sancoes` por `sancao_orgao` |

Desde 15/11/2026 o `buscar_empresas` do MCP tem **todos os filtros da
[API REST](https://empresas.brunokobi.tech/docs)**, além dos clássicos (município, CNAE,
porte, pendências, sanções, processos, benefícios, contratos PNCP, ambiental):

| Filtro | O que exige |
|---|---|
| `cnpj` | CNPJ (14 dígitos) ou raiz (8) |
| `nivel_integridade` | Nível da nota de risco de integridade: `Baixo`, `Moderado`, `Alto`, `Crítico` |
| `com_ocorrencia_socio` / `ocorrencia_fonte` / `ocorrencia_criterio_forte` | Due diligence dos sócios (PGFN PF, servidor, CEAF, Bolsa Família, IBAMA, BCB, CVM, OFAC/ONU/UK, ICIJ) |
| `com_socio_estrangeiro` / `socio_estrangeiro_gafi` | Sócio no exterior / em país da lista do GAFI |
| `com_grupo_economico` / `grupo_relacao` / `grupo_min_empresas` | Ligação societária com outras empresas (base nacional da Receita) |
| `processo_validacao` | Com `com_processos`: só processos com vínculo conferido (`cnpj_confirmado`, `nome_unico_brasil`...) |
| `com_devedor_contumaz` | Lista de devedores contumazes de ICMS da SEFAZ-ES |
| `com_insolvencia` | Recuperação judicial / falência (marcador da Receita na razão social) |
| `com_par_es` | Processo anticorrupção (PAR) no Governo do ES — SECONT |
| `com_contrato_tcees` / `com_contrato_estadual_es` | Contrato com prefeitura/órgão do ES (TCEES) / com o Governo do ES (SEGER) |
| `beneficio_tipo` | Inclui `INVEST_ES` além de `COMPETE_ES`, `RENUNCIA`, `IMUNE_ISENTO`, `HABILITADO` |
| `com_site` / `com_rede_social` / `com_whatsapp` | Site confirmado, rede social e WhatsApp publicados no site da empresa (`redes_sociais`; dado provável, a coleta começa pelas maiores empresas) |

`obter_empresa` devolve todos os blocos do modal: nota de integridade com fatores, due
diligence, grupo econômico, risco-país, redes sociais, devedor contumaz, recuperação
judicial, PAR, contratos TCEES e estaduais, dívida ativa (incluindo FGTS e previdenciário)
e benefícios (incluindo INVEST-ES). `estatisticas` traz em `empresas_por_flag` a contagem
de cada filtro.

Exemplos de perguntas: *"quantas empresas ativas há em Vila Velha?"*, *"restaurantes
em Vitória com e-mail e sem dívida ativa"*, *"classifique como lead de contabilidade
as empresas da Serra com dívida"*, *"mostre a visão 360 do CNPJ 12345678000190"*,
*"algum sócio dessa empresa é PEP ou já foi candidato?"*, *"quais empresas tem num
raio de 5km da Praça Costa Pereira, em Vitória?"*, *"essa empresa já teve contrato
com algum órgão público federal?"*, *"quais candidatos mais receberam doação eleitoral
e quais empresas mais doaram?"*.

Tem **duas formas** de conectar: usar o **servidor remoto** já publicado (nada pra
instalar) ou rodar **localmente** (stdio, se quiser seu próprio dataset/instância).

---

# 🌐 Opção A — Servidor remoto (recomendado, sem instalar nada)

URL do servidor MCP (Streamable HTTP):

```
https://empresas.brunokobi.tech/mcp/
```

> Repare na **barra final** (`/mcp/`) — sem ela alguns clientes recebem um
> redirect e podem não seguir automaticamente.

### 🟢 Claude Code
Arquivo `.mcp.json` (raiz do projeto ou `~/.claude/.mcp.json` para todos os projetos):
```json
{
  "mcpServers": {
    "grande-vitoria-empresas": {
      "type": "http",
      "url": "https://empresas.brunokobi.tech/mcp/"
    }
  }
}
```
Ou via CLI, de qualquer lugar:
```bash
claude mcp add --transport http grande-vitoria-empresas https://empresas.brunokobi.tech/mcp/
```

### 🔵 Cursor
`~/.cursor/mcp.json` (global) ou `.cursor/mcp.json` (no projeto):
```json
{
  "mcpServers": {
    "grande-vitoria-empresas": {
      "url": "https://empresas.brunokobi.tech/mcp/"
    }
  }
}
```

### 🌊 Windsurf (Codeium)
`~/.codeium/windsurf/mcp_config.json` — repare que a chave é `serverUrl`, não `url`:
```json
{
  "mcpServers": {
    "grande-vitoria-empresas": {
      "serverUrl": "https://empresas.brunokobi.tech/mcp/"
    }
  }
}
```

### 🧩 VS Code (GitHub Copilot — agent mode)
`.vscode/mcp.json` (raiz é `servers`, não `mcpServers`):
```json
{
  "servers": {
    "grande-vitoria-empresas": {
      "type": "http",
      "url": "https://empresas.brunokobi.tech/mcp/"
    }
  }
}
```

### 🤖 Cline
`cline_mcp_settings.json` — `type` explícito é obrigatório:
```json
{
  "mcpServers": {
    "grande-vitoria-empresas": {
      "type": "streamableHttp",
      "url": "https://empresas.brunokobi.tech/mcp/"
    }
  }
}
```

### 🟣 Claude Desktop
O app desktop **não** aceita servidor remoto direto no `claude_desktop_config.json`
(esse formato é só para `stdio` local). Duas opções:
- **Interface:** *Settings → Connectors → Add custom connector* → cole a URL acima
  (precisa de plano Pro/Max/Team/Enterprise).
- **Wrapper stdio** (`mcp-remote`), se preferir manter tudo no JSON:
  ```json
  {
    "mcpServers": {
      "grande-vitoria-empresas": {
        "command": "npx",
        "args": ["mcp-remote", "https://empresas.brunokobi.tech/mcp/"]
      }
    }
  }
  ```

### 💬 ChatGPT
Ainda não conecta servidores MCP como os acima. Use a **API REST**:
`https://empresas.brunokobi.tech/docs`.

---

# 💻 Opção B — Rodar localmente (stdio)

Para quem quer seu próprio dataset/instância, ou customizar o servidor.

## Passo 1 — Baixar e instalar

```bash
git clone https://github.com/brunokobi/projeto_grande_vitoria_empresas.git
cd projeto_grande_vitoria_empresas
bash setup.sh          # cria .venv, instala deps e baixa o dataset (Release)
```

## Passo 2 — Descobrir os caminhos absolutos

O MCP precisa do caminho completo do Python do `.venv` e do `mcp_server.py`.
Rode **dentro da pasta do projeto**:

```bash
echo "$(pwd)/.venv/bin/python"
echo "$(pwd)/mcp_server.py"
```

Guarde esses dois caminhos — use-os no lugar de `CAMINHO_PYTHON` e `CAMINHO_SERVER`
nos exemplos abaixo.

> **Windows:** o Python fica em `...\.venv\Scripts\python.exe` (barra invertida).

---

## Passo 3 — Configurar na sua IA

O formato é quase idêntico em todas. É só apontar `command` para o Python do
`.venv` e `args` para o `mcp_server.py`.

### 🟣 Claude Desktop
Edite o arquivo `claude_desktop_config.json`
(**macOS:** `~/Library/Application Support/Claude/` · **Windows:** `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "grande-vitoria-empresas": {
      "command": "CAMINHO_PYTHON",
      "args": ["CAMINHO_SERVER"]
    }
  }
}
```
Salve e **reinicie o Claude Desktop**. As ferramentas aparecem no ícone 🔌.

### 🟢 Claude Code
Já vem pronto: o repositório tem um **`.mcp.json`** na raiz — abra a pasta do
projeto com o Claude Code e ele detecta automaticamente (aceite quando perguntar).
Ou, de qualquer lugar:
```bash
claude mcp add grande-vitoria-empresas -- CAMINHO_PYTHON CAMINHO_SERVER
```

### 🔵 Cursor
Crie/edite `~/.cursor/mcp.json` (global) ou `.cursor/mcp.json` (no projeto):
```json
{
  "mcpServers": {
    "grande-vitoria-empresas": {
      "command": "CAMINHO_PYTHON",
      "args": ["CAMINHO_SERVER"]
    }
  }
}
```
Depois: *Settings → MCP* → confirme que está "verde".

### 🌊 Windsurf (Codeium)
*Settings → Cascade → MCP Servers → Add*, ou edite
`~/.codeium/windsurf/mcp_config.json`:
```json
{
  "mcpServers": {
    "grande-vitoria-empresas": {
      "command": "CAMINHO_PYTHON",
      "args": ["CAMINHO_SERVER"]
    }
  }
}
```

### 🧩 VS Code (GitHub Copilot — agent mode)
Crie `.vscode/mcp.json` no projeto (formato do VS Code usa `servers` + `type`):
```json
{
  "servers": {
    "grande-vitoria-empresas": {
      "type": "stdio",
      "command": "CAMINHO_PYTHON",
      "args": ["CAMINHO_SERVER"]
    }
  }
}
```
Abra o Chat em **Agent mode** e as ferramentas ficam disponíveis.

### 🤖 Cline (extensão do VS Code)
No painel do Cline → *MCP Servers → Configure* (arquivo `cline_mcp_settings.json`):
```json
{
  "mcpServers": {
    "grande-vitoria-empresas": {
      "command": "CAMINHO_PYTHON",
      "args": ["CAMINHO_SERVER"]
    }
  }
}
```

### 💬 ChatGPT
O ChatGPT (app/desktop) ainda **não** conecta servidores MCP locais como os
acima — o suporte a MCP é voltado a conectores remotos/empresariais. Para usar o
dataset com o ChatGPT, prefira a **API REST** (`uvicorn api:app`, docs em `/docs`).

---

## Passo 4 — Testar

Na sua IA, pergunte algo como:

> "Use a ferramenta estatisticas e me diga quantas empresas ativas há na base."

Se responder com os números do dataset, está conectado. 🎉

---

## Alternativa sem MCP: API REST

Se seu cliente não suporta MCP, tudo também está disponível por HTTP:
- **Remoto (já no ar):** `https://empresas.brunokobi.tech/docs`
- **Local:**
  ```bash
  source .venv/bin/activate
  uvicorn api:app      # http://localhost:8000/docs
  ```

## Problemas comuns
- **Servidor remoto — ferramentas não aparecem:** confira a **barra final** na
  URL (`/mcp/`) e se o `type`/chave de transporte está certo pro seu cliente
  (`http`, `sse` ou `streamableHttp` — varia por cliente, veja a Opção A acima).
  Reinicie o cliente depois de editar o config.
- **Local — ferramentas não aparecem:** confira se os caminhos são **absolutos**
  e se rodou o `bash setup.sh` (o `.venv` precisa existir). Reinicie o cliente.
- **"dataset não encontrado":** rode `bash setup.sh` de novo (ele baixa o
  `data/grande_vitoria.db` do Release).
- **Windows:** use `...\.venv\Scripts\python.exe` e barras invertidas nos caminhos.
