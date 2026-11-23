"""Unidades, produtos e estoque."""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from raizesdonordeste.security.autenticacao import publico, requer
from raizesdonordeste.service import estoque_service, produto_service, unidade_service

unidades_bp = Blueprint("unidades", __name__)
produtos_bp = Blueprint("produtos", __name__)
estoque_bp = Blueprint("estoque", __name__)


# ------------------------------------ Unidades ---------------------------------------
@unidades_bp.post("/unidades")
@requer("ADMIN")
def criar_unidade():
    """Criar unidade"""
    return jsonify(unidade_service.criar()), 201


@unidades_bp.get("/unidades")
@requer()
def listar_unidades():
    """Listar unidades ativas (paginado)"""
    return jsonify(unidade_service.listar()), 200


@unidades_bp.get("/unidades/<int:unidade_id>")
@requer()
def buscar_unidade(unidade_id):
    """Buscar unidade por ID"""
    return jsonify(unidade_service.buscar(unidade_id)), 200


@unidades_bp.put("/unidades/<int:unidade_id>")
@requer("ADMIN")
def atualizar_unidade(unidade_id):
    """Atualizar unidade"""
    return jsonify(unidade_service.atualizar(unidade_id)), 200


@unidades_bp.delete("/unidades/<int:unidade_id>")
@requer("ADMIN")
def desativar_unidade(unidade_id):
    """Desativar unidade (exclusão lógica)"""
    unidade_service.desativar(unidade_id)
    return "", 204


# ------------------------------------ Produtos ---------------------------------------
@produtos_bp.get("/produtos")
@publico
def listar_produtos():
    """Listar produtos ativos (paginado)"""
    return jsonify(produto_service.listar()), 200


@produtos_bp.get("/produtos/unidade/<int:unidade_id>")
@requer()
def listar_produtos_da_unidade(unidade_id):
    """Listar disponibilidade de produtos por unidade (paginado)

    Itens sem saldo retornam `disponivel: false` e não podem ser vendidos.
    """
    return jsonify(produto_service.listar_por_unidade(unidade_id)), 200


@produtos_bp.get("/produtos/<int:produto_id>")
@publico
def buscar_produto(produto_id):
    """Buscar produto por ID"""
    return jsonify(produto_service.buscar(produto_id)), 200


@produtos_bp.post("/produtos")
@requer("ADMIN", "GERENTE")
def criar_produto():
    """Criar produto"""
    return jsonify(produto_service.criar()), 201


@produtos_bp.put("/produtos/<int:produto_id>")
@requer("ADMIN", "GERENTE")
def atualizar_produto(produto_id):
    """Atualizar produto"""
    return jsonify(produto_service.atualizar(produto_id)), 200


@produtos_bp.delete("/produtos/<int:produto_id>")
@requer("ADMIN", "GERENTE")
def desativar_produto(produto_id):
    """Desativar produto (soft-delete)"""
    produto_service.desativar(produto_id)
    return "", 204


# ------------------------------------- Estoque ---------------------------------------
@estoque_bp.post("/estoque")
@requer("ADMIN", "GERENTE")
def criar_estoque():
    """Criar registro de estoque (ADMIN ou GERENTE da unidade)"""
    return jsonify(estoque_service.criar(g.usuario)), 201


@estoque_bp.get("/estoque/unidade/<int:unidade_id>")
@requer("ADMIN", "GERENTE")
def listar_estoque_da_unidade(unidade_id):
    """Listar estoque por unidade (paginado)"""
    return jsonify(estoque_service.listar_por_unidade(g.usuario, unidade_id)), 200


@estoque_bp.get("/estoque/<int:estoque_id>")
@requer("ADMIN", "GERENTE")
def buscar_estoque(estoque_id):
    """Buscar estoque por ID"""
    return jsonify(estoque_service.buscar(g.usuario, estoque_id)), 200


@estoque_bp.put("/estoque/<int:estoque_id>")
@requer("ADMIN", "GERENTE")
def atualizar_estoque(estoque_id):
    """Atualizar quantidade (ajuste auditado)"""
    return jsonify(estoque_service.atualizar(g.usuario, estoque_id)), 200


@estoque_bp.delete("/estoque/<int:estoque_id>")
@requer("ADMIN", "GERENTE")
def remover_estoque(estoque_id):
    """Remover registro de estoque (remoção lógica; a trilha é preservada)"""
    estoque_service.remover(g.usuario, estoque_id)
    return "", 204


@estoque_bp.post("/estoque/<int:estoque_id>/movimentacoes")
@requer("ADMIN", "GERENTE")
def registrar_movimentacao(estoque_id):
    """Registrar entrada ou saída

    Saídas manuais nunca tornam o saldo negativo. Guarda quantidade, motivo, saldos e responsável pseudonimizado.
    """
    return jsonify(estoque_service.movimentar(g.usuario, estoque_id)), 201


@estoque_bp.get("/estoque/<int:estoque_id>/movimentacoes")
@requer("ADMIN", "GERENTE")
def listar_movimentacoes(estoque_id):
    """Consultar histórico auditável de movimentações (paginado)"""
    return jsonify(estoque_service.listar_movimentacoes(g.usuario, estoque_id)), 200
