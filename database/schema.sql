-- Schema do dataset de empresas da Grande Vitória
-- SQLite. CNPJ (14 dígitos, sem máscara) é a chave universal de junção.

CREATE TABLE IF NOT EXISTS empresas (
    cnpj                TEXT PRIMARY KEY,
    razao_social        TEXT,
    nome_fantasia       TEXT,
    cnae_principal      TEXT,
    cnae_secundarios    TEXT,        -- lista separada por vírgula
    situacao_cadastral  TEXT,
    data_situacao       TEXT,
    porte               TEXT,
    capital_social      REAL,
    municipio           TEXT,
    uf                  TEXT,
    logradouro          TEXT,
    numero              TEXT,
    bairro              TEXT,
    cep                 TEXT,
    telefone            TEXT,
    email               TEXT,
    regime_tributario   TEXT,        -- Simples / MEI / Normal
    data_ultima_atualizacao TEXT
);

CREATE TABLE IF NOT EXISTS socios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_empresa    TEXT NOT NULL REFERENCES empresas(cnpj),
    nome_socio      TEXT,
    cpf_parcial     TEXT,           -- CPF mascarado, conforme já vem da RF
    qualificacao    TEXT,           -- código de qualificação do sócio
    data_entrada    TEXT,
    faixa_etaria    TEXT            -- código de faixa etária da RF
);

CREATE TABLE IF NOT EXISTS processos_judiciais (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_empresa                TEXT NOT NULL REFERENCES empresas(cnpj),
    numero_processo             TEXT,
    tribunal                    TEXT,
    classe                      TEXT,
    assunto                     TEXT,
    polo                        TEXT,      -- autor / réu
    status                      TEXT,
    data_ultima_movimentacao    TEXT,
    match_confianca             TEXT       -- 'direto' (CNPJ explícito) ou 'fuzzy'
);

CREATE TABLE IF NOT EXISTS sancoes_administrativas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_empresa        TEXT NOT NULL REFERENCES empresas(cnpj),
    tipo                TEXT,       -- CEIS / CNEP / CEPIM / TCEES ...
    motivo              TEXT,
    orgao_sancionador   TEXT,
    data_inicio         TEXT,
    data_fim            TEXT,
    valor_multa         REAL,
    fundamentacao       TEXT,       -- fundamentação legal (CEIS/CNEP)
    numero_processo     TEXT,       -- TCEES
    ano_processo        TEXT,       -- TCEES
    numero_deliberacao  TEXT,       -- TCEES
    ano_deliberacao     TEXT,       -- TCEES
    match_confianca     TEXT
);

CREATE TABLE IF NOT EXISTS infracoes_ambientais (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_empresa      TEXT NOT NULL REFERENCES empresas(cnpj),
    orgao             TEXT,       -- IBAMA / IEMA
    tipo_infracao     TEXT,       -- DES_INFRACAO
    valor_multa       REAL,       -- VAL_AUTO_INFRACAO
    status            TEXT,       -- DS_SIT_AUTO_AIE (situação do auto)
    data_auto         TEXT,       -- DAT_HORA_AUTO_INFRACAO
    gravidade         TEXT,       -- GRAVIDADE_INFRACAO
    tipo_multa        TEXT,       -- TIPO_MULTA
    numero_auto       TEXT,       -- NUM_AUTO_INFRACAO
    municipio_infracao TEXT,      -- MUNICIPIO
    uf_infracao       TEXT,       -- UF
    enquadramento     TEXT,       -- DS_ENQUADRAMENTO_ADMINISTRATIVO
    match_confianca   TEXT
);

CREATE TABLE IF NOT EXISTS dividas_ativas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_empresa        TEXT NOT NULL REFERENCES empresas(cnpj),
    orgao               TEXT,       -- PGFN / Sefaz-ES
    valor               REAL,
    situacao            TEXT,
    data_inscricao      TEXT,
    tipo_tributo        TEXT,       -- RECEITA_PRINCIPAL (ex.: PIS, IRPJ, COFINS)
    numero_inscricao    TEXT,       -- NUMERO_INSCRICAO
    ajuizada            TEXT,       -- INDICADOR_AJUIZADO (SIM/NAO)
    tipo_devedor        TEXT,       -- PRINCIPAL / CORRESPONSAVEL
    unidade_responsavel TEXT        -- UNIDADE_RESPONSAVEL (unidade da PGFN)
);

CREATE TABLE IF NOT EXISTS registros_jucees (
    cnpj_empresa            TEXT PRIMARY KEY REFERENCES empresas(cnpj),
    nire                    TEXT,
    data_constituicao       TEXT,
    nome_fantasia_jucees    TEXT,
    cod_natureza_juridica   TEXT,
    natureza_juridica       TEXT,
    atividade_principal_jucees TEXT,
    data_atualizacao        TEXT
);

CREATE TABLE IF NOT EXISTS enriquecimento_places (
    cnpj_empresa        TEXT PRIMARY KEY REFERENCES empresas(cnpj),
    place_id            TEXT,
    latitude            REAL,
    longitude           REAL,
    telefone_atualizado TEXT,
    site                TEXT,
    avaliacao           REAL,
    total_avaliacoes    INTEGER,
    horario_funcionamento TEXT,
    data_enriquecimento TEXT
);

CREATE TABLE IF NOT EXISTS enriquecimento_contato (
    cnpj_empresa        TEXT PRIMARY KEY REFERENCES empresas(cnpj),
    whatsapp            TEXT,   -- link wa.me derivado do telefone (não verificado)
    site                TEXT,   -- inferido do domínio do e-mail corporativo
    instagram           TEXT,
    facebook            TEXT,
    linkedin            TEXT,
    data_enriquecimento TEXT
);

-- Índices para acelerar os cruzamentos
CREATE INDEX IF NOT EXISTS idx_empresas_municipio ON empresas(municipio);
CREATE INDEX IF NOT EXISTS idx_empresas_cnae ON empresas(cnae_principal);
CREATE INDEX IF NOT EXISTS idx_socios_cnpj ON socios(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_socios_cpf ON socios(cpf_parcial);
CREATE INDEX IF NOT EXISTS idx_jucees_cnpj ON registros_jucees(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_processos_cnpj ON processos_judiciais(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_sancoes_cnpj ON sancoes_administrativas(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_ambiental_cnpj ON infracoes_ambientais(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_dividas_cnpj ON dividas_ativas(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_contato_cnpj ON enriquecimento_contato(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_empresas_capital ON empresas(capital_social);
