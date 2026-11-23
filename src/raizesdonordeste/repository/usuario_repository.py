from __future__ import annotations

from raizesdonordeste.util.tempo import agora_iso


def buscar(conn, usuario_id: int):
    return conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()


def buscar_por_email(conn, email: str):
    return conn.execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()


def inserir(conn, nome, email, senha_hash, perfil, unidade_id=None, telefone=None, cpf=None) -> int:
    return conn.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, perfil, unidade_id, telefone, cpf, criado_em)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (nome, email, senha_hash, perfil, unidade_id, telefone, cpf, agora_iso())).lastrowid


def contar(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]


def outros_admins_ativos(conn, excluir_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM usuarios WHERE perfil='ADMIN' AND ativo=1 AND id<>?",
                        (excluir_id,)).fetchone()[0]
