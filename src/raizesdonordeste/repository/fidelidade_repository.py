from __future__ import annotations

from raizesdonordeste.util.tempo import agora_iso


def consentimento_ativo(conn, usuario_id: int, versao_vigente: str) -> bool:
    evento = conn.execute(
        "SELECT tipo, versao FROM consentimentos_fidelidade WHERE usuario_id=? ORDER BY id DESC LIMIT 1",
        (usuario_id,)).fetchone()
    return bool(evento and evento["tipo"] == "CONCESSAO" and evento["versao"] == versao_vigente)


def movimentar_pontos(conn, usuario_id: int, pontos: int, motivo: str, pedido_id: int | None = None) -> None:
    """Soma `pontos` (positivo ou negativo) ao saldo e registra no extrato. O saldo pode
    ficar negativo (devedor) após estornos; créditos futuros amortizam a dívida."""
    conn.execute("UPDATE usuarios SET pontos = pontos + ? WHERE id=?", (pontos, usuario_id))
    conn.execute("INSERT INTO fidelidade_movimentos (usuario_id, pedido_id, pontos, motivo, criado_em)"
                 " VALUES (?,?,?,?,?)", (usuario_id, pedido_id, pontos, motivo, agora_iso()))
