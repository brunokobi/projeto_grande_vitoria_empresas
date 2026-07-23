# 🔌 Como conectar o dataset via MCP

Este projeto expõe um **servidor MCP** (Model Context Protocol) — ou seja, você
pergunta em linguagem natural na sua IA e ela consulta o dataset de empresas da
Grande Vitória direto, com estas ferramentas:

| Ferramenta | O que faz |
|---|---|
| `estatisticas` | Panorama geral (totais, por município/porte/CNAE) |
| `buscar_empresas` | Busca com filtros (segmento, município, pendências, contato…) |
| `obter_empresa` | Visão 360º de um CNPJ (sócios+rede, dívidas, sanções, infrações) |
| `classificar_empresas` | Pontua/ranqueia leads por objetivo comercial (score 0–100) |

Exemplos de perguntas: *"quantas empresas ativas há em Vila Velha?"*, *"restaurantes
em Vitória com e-mail e sem dívida ativa"*, *"classifique como lead de contabilidade
as empresas da Serra com dívida"*, *"mostre a visão 360 do CNPJ 12345678000190"*.

---

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
```bash
source .venv/bin/activate
uvicorn api:app      # http://localhost:8000/docs
```

## Problemas comuns
- **Ferramentas não aparecem:** confira se os caminhos são **absolutos** e se
  rodou o `bash setup.sh` (o `.venv` precisa existir). Reinicie o cliente.
- **"dataset não encontrado":** rode `bash setup.sh` de novo (ele baixa o
  `data/grande_vitoria.db` do Release).
- **Windows:** use `...\.venv\Scripts\python.exe` e barras invertidas nos caminhos.
