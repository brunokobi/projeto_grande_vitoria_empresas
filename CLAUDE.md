# CLAUDE.md — Contexto do projeto para o Claude Code

Este arquivo é carregado automaticamente pelo Claude Code. Ele resume o
estado do projeto, as decisões tomadas e as **armadilhas já descobertas e
corrigidas** — para não repetir investigação em outra máquina.

## O que é

**Produto de consumo** de um dataset de **empresas ativas da Grande Vitória
(ES)** — Vitória, Vila Velha, Serra, Cariacica, Viana, Guarapari, Fundão —
montado a partir de fontes públicas oficiais (Receita Federal, JUCEES, PGFN,
CGU, TCEES, IBAMA, MTE, DJEN/DataJud do CNJ, TSE, PNCP, INPI, GeoBases-ES,
listas internacionais etc.). Este repositório (público) tem o **dashboard**
(`dashboard/index.html`), a **API REST** (`api.py`), o **servidor MCP**
(`mcp_server.py`) e o `refresh_dataset.py`, que mantém o banco de produção
em dia.

A **extração** (ETL) fica no repositório privado
`grande_vitoria_empresas_extracao`. O registro detalhado de cada fonte e
cruzamento está em `docs/EXTRACAO_E_CRUZAMENTOS.md` naquele repo. Como ele é
privado, não linke esse arquivo em texto público (README, página de fontes):
só mencione que o registro existe.

`main.py` e os módulos de ingestão em `src/` (`cnpj_ingest`, `djen_client`,
`geo_enrich`, `contato_enrich`...) são uma versão antiga do pipeline, que
ficou aqui. A coleta atual (sócios, TSE, PNCP, due diligence, redes sociais,
DataJud em lote, grupo econômico etc.) só existe no repo de extração.

## Como rodar (consumo)

```bash
bash setup.sh                    # uv + Python 3.12 em .venv, deps e dataset do Release
source .venv/bin/activate
uvicorn api:app                  # dashboard em http://localhost:8000, API em /docs
python mcp_server.py             # MCP via stdio (o .mcp.json da raiz já aponta pra ele)
```

O banco (`data/grande_vitoria.db`) vem do Release `dataset-latest` deste
repo; `python3 refresh_dataset.py --force` baixa a versão mais nova.

## Estado atual (API de produção, 15/11/2026)

Números de `GET https://empresas.brunokobi.tech/estatisticas`. Mudam a cada
publicação; arredondados.

| Item | Valor |
|---|---|
| Empresas ativas | 366.995 |
| Sócios | ~243 mil |
| Processos judiciais (DJEN) | ~5,2 milhões de registros; ~94,8 mil empresas como ré (sem os homônimos descartados) |
| Dívida ativa (PGFN) | ~201 mil inscrições em ~39,6 mil empresas |
| Sanções administrativas | 346 registros / 195 empresas; flags: CEPIM 11 empresas, Lista Suja 2, leniência 0 |
| Infrações IBAMA | 1.340 registros / 644 empresas |
| Due diligence dos sócios | ~26,5 mil empresas com alguma ocorrência (PGFN PF em ~24,2 mil) |
| Grupo econômico (base nacional) | ~82 mil empresas |
| Sócio estrangeiro | 914 empresas (8 com país da lista do GAFI) |
| Geocodificação | 100% (`enriquecimento_places` = total de empresas) |
| Nota de integridade | metodologia v1.2 (nov/2026: v1.1 + devedor contumaz de ICMS e contratos TCEES/estaduais), pré-calculada para todas as empresas |

Fontes **sem registro** em produção: acordos de leniência, TCU inabilitados
(a API do TCU estava fora do ar na coleta) e OFAC/ONU/Reino Unido (nenhuma
correspondência até agora).

## Produção e publicação

- **VPS:** `vpsrafa` (Oracle Cloud, Frankfurt, `130.61.140.66`). Site:
  https://empresas.brunokobi.tech. A VPS antiga (`vpsbruno`,
  `129.213.96.52`) foi reclamada pela Oracle em 20/09/2026; o domínio
  `empresas.brunokobi.duckdns.org` não responde mais.
- **Dashboard/API/MCP:** serviço systemd `gv-dashboard`, em
  `/home/ubuntu/apps/projeto_grande_vitoria_empresas`. **Não** é mais
  Coolify e **não** há git no servidor: deploy = copiar os arquivos +
  `sudo systemctl restart gv-dashboard`. O comentário do `start.sh` ainda
  cita o Coolify.
- **Atualização do banco:** cron `30 */2 * * *` do usuário `ubuntu` roda
  `refresh_dataset.py`. Ele só baixa se o asset do Release mudou, garante os
  índices de `grupo_economico`/`risco_pais_socios`, pré-calcula a nota de
  integridade (`src/integridade_lote.py`, ~10 min), confere o banco e troca
  o arquivo com `os.replace` (sem restart).
- **Publicação do dataset:** o container `geo` do ETL, na mesma VPS, publica
  o Release a cada 2h (cron `0 */2` UTC, `vps-publicar-2h.sh`).
- **Onde cada coleta roda:**
  - Site e redes sociais (`src/redes_sociais.py`) e DataJud em lote
    (`src/datajud_lote.py`): 24/7 dentro do container `geo` desde
    15/11/2026, supervisionadas pelos crons `vps-redes-sociais.sh` e
    `vps-datajud-lote.sh`.
  - DJEN: só na máquina local do autor (a API do DJEN recusa IP de fora do
    Brasil); publicado com `scripts/djen-refresh.sh` do repo de extração.
  - Atualização mensal das demais fontes: cron `vps-atualizar-mensal.sh` no
    container `geo`.

**Achado ao reconferir `sancoes_administrativas` (08/08/2026, base antiga)**:
parte das empresas positivas tinha `match_confianca='socio'` (marcada só por
ter sócio em comum com entidade sancionada — ocorre dentro do CEIS); na época,
~22%. Relevante para quem consome este dataset em `experimento2026`: risco de
circularidade com a hipótese de metapath sócio-comum daquela dissertação (ver
`docs/research_plan.md`, seções 5 e 9, naquele repo).

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

6. **Variável de ambiente vazia não usa o default.** `os.environ.get(k, default)`
   NÃO usa o default quando a var existe mas está vazia (`source .env` a
   define como ""). Use `os.environ.get(k) or FALLBACK` (é o que faz
   `src/processo_detalhes.py` com `DATAJUD_API_KEY`).

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

## Consumo do dataset (implementado)

- **Servidor MCP** (`mcp_server.py`, FastMCP): ferramentas `estatisticas`,
  `buscar_empresas`, `buscar_empresas_perto`, `obter_empresa`,
  `classificar_empresas`, `ranking_doacoes_eleitorais`, `classes_processos`
  e `orgaos_sancionadores`. Remoto em `https://empresas.brunokobi.tech/mcp/`
  (montado em `/mcp` pela API); local via `.mcp.json`. Desde 15/11/2026 o
  `buscar_empresas` do MCP tem os mesmos filtros da API (ver `MCP.md`); ao
  criar filtro novo em `api.filtros_comuns`, acrescente também no
  `mcp_server.buscar_empresas`.
- **API REST** (`api.py`, FastAPI): `/estatisticas`, `/empresas` (com
  filtros), `/empresas/{cnpj}`, `/empresas/perto`, `/mapa`,
  `/empresas/{cnpj}/midia`, `/processos/{numero}/detalhes`, `/classificar`,
  `/export/empresas.xlsx|pdf` e outras. Docs em `/docs`.
- **Dashboard web** (`dashboard/index.html`, servido em `/` pela API): mapa
  (MapLibre), filtros, visão 360º por empresa em modal, export Excel/PDF. A
  página de fontes é a função `abrirSobre()` (botão **?**) — revisada contra
  código e produção em 15/11/2026; use como referência do que cada fonte é e
  das ressalvas.
- Todos usam `src/dataset_queries.py` (SQLite somente-leitura) — sem duplicar
  SQL. A nota de integridade é `src/avaliacao_integridade.py` (mesma função no
  modal e no pré-cálculo em lote).
- **Dossiê de IA:** vem do repo privado `kobi-intelligence-hub` (chamado em
  `/kobi-api/dossie/...`). Índice principal = nota de integridade; scores de
  XGBoost e de uma GNN são sinais auxiliares; parecer redigido por LLM gratuito
  do OpenRouter (padrão `llama-3.1-8b-instruct`, com troca para outro modelo
  gratuito quando indisponível).
- Doação: `.github/FUNDING.yml` → GitHub Sponsors (`brunokobi`).

## Contas, cota mensal e doação (20/11/2026)

- **Regra:** busca/filtros/mapa/estatísticas livres. Relatório (visão 360º,
  `GET /empresas/{cnpj}` e o `obter_empresa` do MCP **remoto**) exige login ou
  chave e gasta cota: 10/mês grátis (`COTA_MENSAL`), mesmo CNPJ no mesmo mês
  não conta de novo. Export, mídia e detalhes de processo pedem login, sem
  cota. MCP local (stdio) não tem limite: `_requisicao_http(ctx)` é `None`.
- **Código:** `src/contas.py` (banco, sessões, chaves, cota, e-mail, Google,
  Pix BR Code) e `src/contas_rotas.py` (rotas `/auth/*`, `/conta*`,
  `/doacao*`). No dashboard: `carregarConta`, `abrirConta`, `renderBloqueio`,
  `abrirDoacao`.
- **Banco separado `data/contas.db`** (ou `CONTAS_DB`). NÃO mover para o
  `grande_vitoria.db`: o `refresh_dataset.py` troca esse arquivo inteiro a
  cada 2h e apagaria os usuários. Tokens, chaves e links guardados só como
  hash SHA-256.
- **Variáveis** (sem elas o método some da tela): `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`, `EMAIL_PROVIDER` (brevo|resend), `EMAIL_API_KEY`,
  `EMAIL_FROM`, `SITE_URL` (padrão o domínio de produção; troque para testar
  local, senão o cookie sai `Secure` e o redirect do Google aponta pra
  produção). O serviço `gv-dashboard` não tinha `EnvironmentFile`: é preciso
  acrescentar para ler o `.env` da pasta do app.
- **Sem nenhum método configurado** (`contas.cadastro_ativo()` falso) o
  site fica aberto como antes: sem cota, sem login, sem botão "Entrar".
- **Link por e-mail** abre uma página com botão (POST) em vez de logar no
  GET: filtros de e-mail corporativo abrem links sozinhos e queimariam o link
  de uso único.
- **Pix:** chave celular do mantenedor em `config.PIX_CHAVE` (pública por
  decisão dele). Doação não dá cota extra.
- Planos e próximas fases: `docs/PLANOS.md`.

## Páginas de SEO (20/11/2026)

`src/seo_paginas.py`: `/empresa/{cnpj}-{slug}`, `/cidade/{slug}`,
`/cidade/{slug}/atividade/{cnae}-{slug}`, `/cidade/{slug}/bairro/{slug}` e
sitemaps (`/sitemap.xml` é índice). Regras que NÃO devem regredir: só dado
cadastral neutro (nada de processos/dívidas/sanções/sócios/nota no HTML
indexável); MEI sem logradouro/número/CEP/mapa/coordenadas; telefone e e-mail
nunca; `data/seo_remocoes.txt` → 410. Cache em memória chaveado pelo mtime do
banco. A tela de privacidade descreve essas páginas.

Cidade/atividade/bairro também em inglês (`/en/city/...`) e espanhol
(`/es/ciudad/...`), textos em `seo_paginas.T` e CNAE em
`reference/cnaes_{en,es}.json` (tradução própria, não oficial). Página de
empresa só em português.

## AdSense

`config.ADSENSE_CLIENT` (env `ADSENSE_CLIENT`, vazio = desligado). Anúncios
automáticos só no `_pagina` de `src/seo_paginas.py` (status 200); NUNCA no
dashboard/relatório. `/ads.txt` em `api.py`. O dashboard recebe
`window.GV_ANUNCIOS=true`, que liga os trechos de anúncios na política de
privacidade.

## MCP com login (OAuth 2.1)

`src/oauth_mcp.py`: `/mcp-conta/` é o mesmo `mcp_app` envolvido por
`ExigirToken` (401 + `WWW-Authenticate` com `resource_metadata`, é o que faz
o claude.ai iniciar o login). `/mcp/` continua aberto. Registro dinâmico,
PKCE S256 obrigatório, token de acesso `gvat_` (24h) e refresh `gvrt_` (90
dias, rotativo), tudo como hash em `contas.db`. `contas.usuario_da_requisicao`
aceita `gvat_` além das chaves `gv_`. Relatório que falha depois de cobrado é
estornado (`contas.estornar`).

## Site e redes sociais × etapa antiga `contato`

- **Atual:** tabela `redes_sociais`, gerada no ETL (`src/redes_sociais.py`
  daquele repo), por raiz de CNPJ. Site só com prova (Registro.br RDAP com o
  mesmo CNPJ, CNPJ exibido no site, ou domínio do e-mail da Receita compatível
  com o nome); redes = links publicados no próprio site (as plataformas não
  são acessadas). No modal aparece em "Contato & redes" como **dado provável,
  pode conter falhas**, com o motivo da aceitação.
- **Antiga:** `src/contato_enrich.py` (`--etapa contato`, tabela
  `enriquecimento_contato`: WhatsApp derivado do telefone, site do e-mail)
  **nunca rodou na base completa**; a tabela publicada está vazia. Desde
  15/11/2026 os filtros `com_site`/`com_rede_social` e a presença digital da
  classificação de leads leem `redes_sociais`. `com_whatsapp`/`pref_whatsapp`
  usam `redes_sociais.whatsapp`: só o WhatsApp que a empresa publica no próprio
  site (não existe forma oficial de checar se um número tem WhatsApp; o
  palpite antigo pelo formato do telefone foi abandonado).
