"""Pedidos e pagamento."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from raizesdonordeste.security.autenticacao import requer
from raizesdonordeste.service import pagamento_service, pedido_service

pedidos_bp = Blueprint("pedidos", __name__)
pagamento_bp = Blueprint("pagamento", __name__)


@pedidos_bp.post("/pedidos")
@requer("CLIENTE", "ATENDENTE")
def criar_pedido():
    """Criar novo pedido; aceita Idempotency-Key

    Reserva o estoque, aplica campanhas, cupom e resgate de pontos. O header opcional `Idempotency-Key`
    (8 a 100 caracteres) é escopado ao usuário: repetir a chave com o mesmo conteúdo devolve o pedido original
    (200, `Idempotency-Replayed: true`); com conteúdo diferente retorna 409 CHAVE_IDEMPOTENCIA_REUTILIZADA.
    """
    pedido, criado = pedido_service.criar(g.usuario, request.headers.get("Idempotency-Key"))
    resposta = jsonify(pedido)
    if not criado:
        resposta.headers["Idempotency-Replayed"] = "true"
    return resposta, (201 if criado else 200)


@pedidos_bp.get("/pedidos")
@requer()
def listar_pedidos():
    """Listar pedidos com filtros combináveis (canalPedido, status, unidadeId)"""
    return jsonify(pedido_service.listar(g.usuario)), 200


@pedidos_bp.get("/pedidos/<int:pedido_id>")
@requer()
def buscar_pedido(pedido_id):
    """Buscar pedido por ID"""
    return jsonify(pedido_service.buscar(g.usuario, pedido_id)), 200


@pedidos_bp.patch("/pedidos/<int:pedido_id>/status")
@requer("COZINHA", "ATENDENTE", "GERENTE", "ADMIN")
def atualizar_status_pedido(pedido_id):
    """Atualizar status operacional (cozinha → pronto → entregue)

    Fluxo: RECEBIDO → EM_PREPARO → PRONTO → ENTREGUE. Para cancelar use o endpoint de cancelamento.
    """
    return jsonify(pedido_service.atualizar_status(g.usuario, pedido_id)), 200


@pedidos_bp.post("/pedidos/<int:pedido_id>/cancelamento")
@requer("CLIENTE", "ATENDENTE", "ADMIN")
def cancelar_pedido(pedido_id):
    """Cancelar o pedido e executar as compensações aplicáveis

    Devolve estoque (até RECEBIDO), estorna pagamento aprovado no gateway, libera cupom e ajusta pontos.
    Gateway indisponível: 503 e o pedido permanece no estado anterior.
    """
    return jsonify(pedido_service.cancelar(g.usuario, pedido_id)), 200


@pagamento_bp.post("/pedidos/<int:pedido_id>/pagamento")
@requer("CLIENTE", "ATENDENTE")
def pagar_pedido(pedido_id):
    """Processar pagamento (gateway simulado)

    Cria uma tentativa e devolve status e payload do gateway. Recusa comercial retorna 201 com `status: RECUSADO`
    e o pedido continua aguardando pagamento; indisponibilidade técnica retorna 503 sem consumir tentativa.
    Em dev/test o header `X-Forcar-Status-Pagamento` (APROVADO, RECUSADO, INDISPONIVEL) torna o resultado
    determinístico; em prod ele é ignorado.
    """
    return jsonify(pagamento_service.pagar(g.usuario, pedido_id)), 201


@pagamento_bp.get("/pedidos/<int:pedido_id>/pagamento/tentativas")
@requer()
def listar_tentativas_pagamento(pedido_id):
    """Consultar o histórico de tentativas de pagamento e estorno"""
    return jsonify(pagamento_service.listar_tentativas(g.usuario, pedido_id)), 200
