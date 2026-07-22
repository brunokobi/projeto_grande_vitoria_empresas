"""Funções auxiliares de conexão e upsert no SQLite."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

import config


def init_db():
    """Cria o banco e aplica o schema, se ainda não existir."""
    schema_path = config.BASE_DIR / "database" / "schema.sql"
    with sqlite3.connect(config.DB_PATH) as conn:
        with open(schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    print(f"[db_utils] Banco inicializado em {config.DB_PATH}")


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_empresa(conn, empresa: dict):
    """Insere ou atualiza uma empresa pela chave CNPJ."""
    cols = ", ".join(empresa.keys())
    placeholders = ", ".join(["?"] * len(empresa))
    updates = ", ".join([f"{k}=excluded.{k}" for k in empresa.keys() if k != "cnpj"])
    sql = f"""
        INSERT INTO empresas ({cols}) VALUES ({placeholders})
        ON CONFLICT(cnpj) DO UPDATE SET {updates}
    """
    conn.execute(sql, list(empresa.values()))


def insert_generic(conn, table: str, row: dict):
    """Insert simples em tabelas satélite (socios, processos, sanções, etc.)."""
    cols = ", ".join(row.keys())
    placeholders = ", ".join(["?"] * len(row))
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    conn.execute(sql, list(row.values()))


def cnpj_existe(conn, cnpj: str) -> bool:
    cur = conn.execute("SELECT 1 FROM empresas WHERE cnpj = ?", (cnpj,))
    return cur.fetchone() is not None


def listar_cnpjs(conn):
    """Retorna todos os CNPJs já carregados na base filtrada (Grande Vitória)."""
    cur = conn.execute("SELECT cnpj, razao_social, municipio FROM empresas")
    return cur.fetchall()
