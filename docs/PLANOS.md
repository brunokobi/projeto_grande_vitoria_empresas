# Planos do projeto

Atualizado em 20/11/2026. Ordem de prioridade decidida com o mantenedor.

## Fase 1 — Cadastro, cota mensal e doação (implementada em 20/11/2026)

- **Cadastro sem senha:** "Entrar com Google" (OAuth 2.0) ou link de acesso
  por e-mail (Brevo ou Resend). Sessão em cookie HttpOnly de 30 dias.
- **Cota:** 10 relatórios completos por mês, grátis. O motivo aparece para o usuário: evitar abuso (robôs copiando a base) e sobrecarga do servidor; quem precisa de mais baixa o banco completo no GitHub. Relatório = visão 360º
  de uma empresa (`GET /empresas/{cnpj}`, o modal do site ou a ferramenta MCP
  `obter_empresa` remota). Rever o mesmo CNPJ no mesmo mês não conta de novo;
  a cota renova no dia 1º (horário de Brasília).
- **Livre, sem cadastro:** busca, filtros, mapa, estatísticas, classificação
  de leads, ranking de doações eleitorais e todas as outras ferramentas MCP.
- **Com login, sem gastar cota:** exportação Excel/PDF, notícias da empresa e
  detalhes de processo.
- **Chave de API** (`gv_...`, até 5 por conta, criada em "Minha conta"): a
  mesma cota no MCP remoto e na API REST, por `Authorization: Bearer`,
  `X-API-Key` ou `?chave=` na URL do MCP.
- **Doação:** Pix (chave celular, QR Code e copia e cola gerados no servidor)
  e GitHub Sponsors. Doação não dá cota extra: se um dia houver plano pago,
  ele fica separado da doação (com benefício em troca vira venda, com nota
  fiscal e imposto).
- **LGPD:** política de privacidade com a seção "Se você cria uma conta" e
  exclusão da conta na hora, pelo próprio usuário.

Ressalva: o banco completo continua público no Release do GitHub. A cota vale
para quem usa o site, a API e o MCP hospedados; quem roda a própria instância
não tem limite.

### Para ativar em produção

1. Google Cloud Console → APIs e serviços → Credenciais → ID do cliente OAuth
   (aplicativo da Web), com o URI de redirecionamento
   `https://empresas.brunokobi.tech/auth/google/callback`.
2. Conta no Brevo (300 e-mails/dia grátis) ou no Resend, com o remetente
   verificado (de preferência o domínio `brunokobi.tech`, com SPF/DKIM, para
   não cair no spam).
3. Na VPS, arquivo `.env` (permissão 600) na pasta do app, com
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `EMAIL_PROVIDER`,
   `EMAIL_API_KEY` e `EMAIL_FROM`, e `EnvironmentFile=` no serviço systemd
   `gv-dashboard`.
4. Sem essas variáveis o método correspondente some da tela. **Sem nenhum
   dos dois, o cadastro fica desligado e o site funciona aberto como antes**
   (sem botão "Entrar", relatório, exportação e MCP sem cota). Por isso o
   código pode subir antes das credenciais: a cota passa a valer sozinha
   quando o primeiro método for configurado e o serviço reiniciado.

## Fase 2 — SEO por CNPJ, cidade e setor (implementada em 20/11/2026, aguardando deploy)

- Páginas geradas no servidor (`src/seo_paginas.py`): `/empresa/{cnpj}-{nome}`,
  `/cidade/{cidade}`, `/cidade/{cidade}/atividade/{cnae}-{nome}` e
  `/cidade/{cidade}/bairro/{bairro}`. As páginas por atividade (CNAE de 7
  dígitos) substituíram a ideia de "setor" e de `/cnae/{codigo}`: casam com
  buscas como "restaurantes em Serra".
- MEI: só bairro e cidade, sem mapa; telefone e e-mail fora de todas as
  páginas; remoção a pedido por `data/seo_remocoes.txt`.
- Depois do deploy: cadastrar o site no Google Search Console e no Bing
  Webmaster Tools, enviar o `sitemap.xml` e acompanhar a indexação (começa
  devagar: de centenas a alguns milhares de páginas nos primeiros meses).
- Só dado cadastral neutro nas páginas indexáveis (razão social, atividade,
  endereço, porte, situação, mapa, empresas próximas e do mesmo setor).
  Processos, dívidas, sanções e nota de integridade ficam no relatório com
  login, fora do Google, para evitar exposição indevida e ações por dano
  moral (empresa também pode pedir indenização, Súmula 227 do STJ).
- Sitemaps divididos (45 mil URLs cada), schema.org `Organization` e
  `BreadcrumbList`, links internos (empresa → atividade → cidade, bairro,
  empresas do mesmo ramo).
- Depois, com tráfego medido: anúncios e afiliados contextuais (contabilidade
  para MEI, conta PJ, certificado digital) nas páginas públicas.

## Fase 3 — Inglês, espanhol e OAuth no MCP (implementada em 20/11/2026, aguardando deploy)

- **Feito:** páginas de cidade, atividade e bairro em `/en/...` e `/es/...`,
  com `hreflang` (também no sitemap, ~13 mil URLs) e seletor de idioma;
  as 1.359 descrições de CNAE traduzidas (`reference/cnaes_en.json`,
  `reference/cnaes_es.json`, tradução própria no estilo ISIC/CIIU Rev.4).
- **Feito:** OAuth 2.1 no MCP: novo endereço `/mcp-conta/` com login, para os
  conectores do claude.ai; "Minha conta" lista e desconecta os aplicativos.
- **Mantido em português:** página de cada empresa (nome, endereço e
  registros não se traduzem; triplicar 366 mil páginas reduziria a indexação).
- **Não feito (decisão pendente):** traduzir a interface do dashboard e o
  modal do relatório. São ~3.300 linhas com textos espalhados em templates
  JavaScript; é uma refatoração grande do produto principal, com risco de
  regressão, para um público (estrangeiro) que hoje chega pelas páginas de
  SEO já traduzidas.

## AdSense (código pronto em 20/11/2026, desligado)

- Variável `ADSENSE_CLIENT=ca-pub-...` no `.env` da VPS liga os anúncios
  automáticos **só nas páginas públicas** (cidade, atividade, bairro e
  empresa, nos 3 idiomas). Dashboard, relatório, conta, login e doação ficam
  sem anúncio; o dashboard recebe só a marca de verificação da conta.
- `GET /ads.txt` passa a declarar o `pub-...` como vendedor autorizado.
- A política de privacidade ganha a seção "Anúncios" (cookies do Google,
  links para as políticas e para desativar anúncios personalizados) só
  quando os anúncios estão ligados.
- No painel do AdSense: adicionar o site `brunokobi.tech`, ativar os
  **anúncios automáticos** e, em **Privacidade e mensagens**, a mensagem de
  consentimento do próprio Google (exigida para visitantes da Europa).
- Risco: o Google pode recusar sites de listas de dados como "conteúdo de
  baixo valor"; as páginas de cidade/atividade/bairro ajudam.

## Planos pagos (implementado em 21/11/2026, aguardando deploy)

| Plano | Relatórios/mês | Mensal | Anual |
|---|---|---|---|
| Grátis | 10 | — | — |
| Profissional | 100 | R$ 19,90 | R$ 9,99/mês = R$ 119,88 de uma vez |
| Empresa | 1.000 | R$ 79,90 | R$ 59,99/mês = R$ 719,88 de uma vez |

- Pagamento por Pix na chave do mantenedor, sem taxa de provedor. O QR Code
  já vem com o valor e o código do pedido. "Já paguei" manda aviso no
  Telegram com um link assinado; o mantenedor confere o extrato e toca em
  "Ativar". A tela do cliente atualiza sozinha.
- Assinante não vê anúncios; visitantes e contas grátis veem (quando o AdSense estiver ligado).
- Sem renovação automática; 7 dias de arrependimento com reembolso (CDC,
  art. 49); doação continua separada e não dá plano.
- Próximo passo quando houver volume: provedor com webhook (Asaas ou Mercado
  Pago, sem mensalidade, com taxa por pagamento) para ativar sem
  intervenção. Antes de cobrar, confirmar com um contador a parte de nota
  fiscal e imposto (pessoa física x MEI).

## Ideias para depois (sem data)

- Relatório de due diligence em PDF por CNPJ.
- Monitoramento por assinatura: alerta quando um CNPJ acompanhado ganhar
  processo, dívida ativa ou sanção.
- "Reivindique sua empresa": o dono confirma o CNPJ e completa o perfil.
