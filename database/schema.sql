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
    qualificacao    TEXT,
    data_entrada    TEXT
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
    tipo                TEXT,       -- CEIS / CNEP / CEPIM / CADE
    motivo              TEXT,
    orgao_sancionador   TEXT,
    data_inicio         TEXT,
    data_fim            TEXT,
    valor_multa         REAL,
    match_confianca     TEXT
);

CREATE TABLE IF NOT EXISTS infracoes_ambientais (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_empresa    TEXT NOT NULL REFERENCES empresas(cnpj),
    orgao           TEXT,       -- IBAMA / IEMA
    tipo_infracao   TEXT,
    valor_multa     REAL,
    status          TEXT,       -- pago / embargado / recorrendo
    data_auto       TEXT,
    match_confianca TEXT
);

CREATE TABLE IF NOT EXISTS dividas_ativas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_empresa    TEXT NOT NULL REFERENCES empresas(cnpj),
    orgao           TEXT,       -- PGFN / Sefaz-ES
    valor           REAL,
    situacao        TEXT,
    data_inscricao  TEXT
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

-- Índices para acelerar os cruzamentos
CREATE INDEX IF NOT EXISTS idx_empresas_municipio ON empresas(municipio);
CREATE INDEX IF NOT EXISTS idx_empresas_cnae ON empresas(cnae_principal);
CREATE INDEX IF NOT EXISTS idx_socios_cnpj ON socios(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_jucees_cnpj ON registros_jucees(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_processos_cnpj ON processos_judiciais(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_sancoes_cnpj ON sancoes_administrativas(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_ambiental_cnpj ON infracoes_ambientais(cnpj_empresa);
CREATE INDEX IF NOT EXISTS idx_dividas_cnpj ON dividas_ativas(cnpj_empresa);
