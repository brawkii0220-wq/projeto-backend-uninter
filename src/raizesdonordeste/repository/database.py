"""Conexão SQLite, transações, migrations (estilo Flyway) e paginação."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import contextmanager
from math import ceil
from pathlib import Path

from flask import current_app, g, request

from raizesdonordeste.exception.api_error import ApiError
from raizesdonordeste.util.tempo import agora_iso

MIGRATION_DIR = Path(__file__).resolve().parent.parent / "resources" / "db" / "migration"
_MIGRATION_RE = re.compile(r"^V(\d+)__(.+)\.sql$")


def abrir_conexao(caminho: str) -> sqlite3.Connection:
    if caminho != ":memory:":
        Path(caminho).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(caminho, isolation_level=None, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if caminho != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def conexao() -> sqlite3.Connection:
    if "db" not in g:
        g.db = abrir_conexao(current_app.extensions["settings"].db_path)
    return g.db


def fechar_conexao(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def transacao():
    """BEGIN IMMEDIATE obtém o bloqueio de escrita já no início, serializando operações
    concorrentes (reserva de estoque, cupons, cancelamentos e campanhas sobrepostas)."""
    conn = conexao()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def migrar(conn: sqlite3.Connection) -> list[int]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS historico_migracoes ("
        " versao INTEGER PRIMARY KEY, descricao TEXT NOT NULL, checksum TEXT NOT NULL, aplicada_em TEXT NOT NULL)")
    aplicadas = {r["versao"]: r["checksum"] for r in conn.execute("SELECT versao, checksum FROM historico_migracoes")}
    novas = []
    for arquivo in sorted(MIGRATION_DIR.glob("V*__*.sql"), key=lambda p: int(_MIGRATION_RE.match(p.name).group(1))):
        versao = int(_MIGRATION_RE.match(arquivo.name).group(1))
        sql = arquivo.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        if versao in aplicadas:
            if aplicadas[versao] != checksum:
                raise RuntimeError(f"Migration V{versao} foi alterada após ser aplicada.")
            continue
        conn.executescript(sql)
        conn.execute("INSERT INTO historico_migracoes VALUES (?,?,?,?)",
                     (versao, _MIGRATION_RE.match(arquivo.name).group(2), checksum, agora_iso()))
        novas.append(versao)
    return novas


def limpar(conn: sqlite3.Connection, perfil: str) -> int:
    """Equivalente ao `flyway clean`: apaga todos os objetos do banco. Bloqueado no perfil prod."""
    if perfil == "prod":
        raise RuntimeError("db-limpar é proibido no perfil prod.")
    conn.execute("PRAGMA foreign_keys = OFF")
    removidos = 0
    for tipo in ("trigger", "view", "table"):      # gatilhos e views antes das tabelas
        for linha in conn.execute("SELECT name FROM sqlite_master WHERE type=? AND name NOT LIKE 'sqlite_%'",
                                  (tipo,)).fetchall():
            conn.execute(f'DROP {tipo.upper()} IF EXISTS "{linha["name"]}"')
            removidos += 1
    conn.execute("PRAGMA foreign_keys = ON")
    return removidos


def ler_paginacao() -> tuple[int, int]:
    """Lê ?page=0&limit=10 (limit máximo 100)."""
    erros = []
    valores = {}
    for nome, padrao, minimo, maximo in (("page", 0, 0, 1_000_000), ("limit", 10, 1, 100)):
        bruto = request.args.get(nome)
        if bruto is None:
            valores[nome] = padrao
            continue
        try:
            numero = int(bruto)
            if not (minimo <= numero <= maximo):
                raise ValueError
            valores[nome] = numero
        except ValueError:
            erros.append({"field": nome, "issue": f"deve ser um inteiro entre {minimo} e {maximo}"})
    if erros:
        raise ApiError(422, "VALIDACAO_ERRO", "Parâmetros de paginação inválidos.", erros)
    return valores["page"], valores["limit"]


def paginar(sql: str, params: list, mapeador) -> dict:
    page, limit = ler_paginacao()
    conn = conexao()
    total = conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
    linhas = conn.execute(f"{sql} LIMIT ? OFFSET ?", [*params, limit, page * limit]).fetchall()
    return {"content": [mapeador(l) for l in linhas], "page": page, "limit": limit,
            "totalElements": total, "totalPages": ceil(total / limit) if total else 0}
