"""Pagamento via gateway simulado: envio, registro de cada tentativa e retorno (status + payload)."""
from __future__ import annotations

from flask import current_app, request

from raizesdonordeste.dto.validacao import Validador, corpo_json
from raizesdonordeste.exception.api_error import ApiError, conflito
from raizesdonordeste.gateway.gateway_pagamento import GatewayIndisponivel
from raizesdonordeste.model.enums import FormaPagamento
from raizesdonordeste.repository import pedido_repository
from raizesdonordeste.repository.database import conexao, transacao
from raizesdonordeste.service import fidelidade_service
from raizesdonordeste.service.pedido_service import carregar_autorizado
from raizesdonordeste.util.tempo import agora_iso

HEADER_SIMULACAO = "X-Forcar-Status-Pagamento"


def _status_forcado() -> str | None:
    """Em dev/test, o header força o resultado do gateway; em prod ele é ignorado."""
    if not current_app.extensions["settings"].simulacao_header_habilitada:
        return None
    valor = request.headers.get(HEADER_SIMULACAO)
    if not valor:
        return None
    valor = valor.strip().upper()
    if valor not in ("APROVADO", "RECUSADO", "INDISPONIVEL"):
        raise ApiError(422, "VALIDACAO_ERRO", f"Header {HEADER_SIMULACAO} inválido.",
                       [{"field": HEADER_SIMULACAO, "issue": "valores aceitos: APROVADO, RECUSADO, INDISPONIVEL"}])
    return valor


def pagar(usuario, pedido_id: int) -> dict:
    v = Validador(corpo_json())
    forma = v.enum("formaPagamento", FormaPagamento.valores())
    v.verificar()
    forcar = _status_forcado()
    gateway = current_app.extensions["gateway"]

    with transacao() as conn:
        pedido = carregar_autorizado(conn, usuario, pedido_id)
        if pedido["status"] != "AGUARDANDO_PAGAMENTO":
            raise conflito("PEDIDO_NAO_AGUARDA_PAGAMENTO",
                           f"O pedido está {pedido['status']} e não aceita novo pagamento.")
        numero = conn.execute("SELECT COUNT(*) FROM pagamento_tentativas WHERE pedido_id=? AND tipo='PAGAMENTO'",
                              (pedido_id,)).fetchone()[0] + 1
        requisicao = {
            "referenciaPedido": f"pedido-{pedido_id}", "tentativa": numero, "formaPagamento": forma,
            "valor": {"centavos": pedido["total_centavos"], "moeda": "BRL"}, "enviadoEm": agora_iso(),
        }
        try:
            resposta = gateway.autorizar(requisicao, forcar)
        except GatewayIndisponivel:
            # Falha técnica: nenhuma tentativa é gravada e o pedido segue aguardando pagamento.
            raise ApiError(503, "GATEWAY_PAGAMENTO_INDISPONIVEL",
                           "O gateway de pagamento está indisponível. O pedido não foi alterado; tente novamente.")

        tentativa_id = pedido_repository.registrar_tentativa(
            conn, pedido_id, "PAGAMENTO", forma, resposta.status, pedido["total_centavos"],
            resposta.referencia, requisicao, resposta.payload)
        pontos = 0
        if resposta.status == "APROVADO":
            conn.execute("UPDATE pedidos SET status='RECEBIDO', status_pagamento='APROVADO', atualizado_em=?"
                         " WHERE id=?", (agora_iso(), pedido_id))
            pedido_repository.registrar_historico(conn, pedido_id, "AGUARDANDO_PAGAMENTO", "RECEBIDO", usuario["id"])
            pontos = fidelidade_service.conceder_por_pagamento(conn, pedido)
        else:
            conn.execute("UPDATE pedidos SET status_pagamento='RECUSADO', atualizado_em=? WHERE id=?",
                         (agora_iso(), pedido_id))
        tentativa = conn.execute("SELECT * FROM pagamento_tentativas WHERE id=?", (tentativa_id,)).fetchone()
        atual = pedido_repository.buscar(conn, pedido_id)
        resultado = pedido_repository.tentativa_dto(tentativa)
        resultado.update({"numeroTentativa": numero, "pedidoStatus": atual["status"],
                          "pedidoStatusPagamento": atual["status_pagamento"], "pontosConcedidos": pontos})
        return resultado


def listar_tentativas(usuario, pedido_id: int) -> list[dict]:
    conn = conexao()
    carregar_autorizado(conn, usuario, pedido_id)
    linhas = conn.execute("SELECT * FROM pagamento_tentativas WHERE pedido_id=? ORDER BY id", (pedido_id,)).fetchall()
    return [pedido_repository.tentativa_dto(t) for t in linhas]
