from __future__ import annotations

from raizesdonordeste.exception.api_error import ApiError
from raizesdonordeste.util.tempo import agora_iso

_SELECT = ("SELECT e.*, p.nome AS produto_nome, p.preco_centavos, p.ativo AS produto_ativo "
           "FROM estoques e JOIN produtos p ON p.id = e.produto_id ")


def buscar(conn, estoque_id: int):
    return conn.execute(_SELECT + "WHERE e.id=?", (estoque_id,)).fetchone()


def buscar_por_unidade_produto(conn, unidade_id: int, produto_id: int):
    return conn.execute(_SELECT + "WHERE e.unidade_id=? AND e.produto_id=?", (unidade_id, produto_id)).fetchone()


def aplicar_movimento(conn, estoque_id: int, tipo: str, quantidade: int, motivo: str,
                      responsavel: str, pedido_id: int | None = None) -> int:
    """Altera o saldo e grava a movimentação auditável. Saída nunca deixa o saldo negativo.
    Deve ser chamada dentro de uma transação (BEGIN IMMEDIATE)."""
    anterior = conn.execute("SELECT quantidade FROM estoques WHERE id=?", (estoque_id,)).fetchone()["quantidade"]
    if tipo == "SAIDA":
        alterado = conn.execute("UPDATE estoques SET quantidade = quantidade - ? WHERE id=? AND quantidade >= ?",
                                (quantidade, estoque_id, quantidade)).rowcount
        if not alterado:
            raise ApiError(409, "ESTOQUE_INSUFICIENTE", "Não há quantidade suficiente para esta saída.",
                           [{"field": "quantidade", "issue": f"Disponível: {anterior}"}])
        posterior = anterior - quantidade
    else:
        conn.execute("UPDATE estoques SET quantidade = quantidade + ? WHERE id=?", (quantidade, estoque_id))
        posterior = anterior + quantidade
    conn.execute(
        "INSERT INTO movimentacoes_estoque (estoque_id, tipo, quantidade, motivo, saldo_anterior,"
        " saldo_posterior, responsavel, pedido_id, criado_em) VALUES (?,?,?,?,?,?,?,?,?)",
        (estoque_id, tipo, quantidade, motivo, anterior, posterior, responsavel, pedido_id, agora_iso()))
    return posterior
