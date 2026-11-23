from __future__ import annotations


def buscar_unidade(conn, unidade_id: int):
    return conn.execute("SELECT * FROM unidades WHERE id=?", (unidade_id,)).fetchone()


def buscar_produto(conn, produto_id: int):
    return conn.execute("SELECT * FROM produtos WHERE id=?", (produto_id,)).fetchone()
