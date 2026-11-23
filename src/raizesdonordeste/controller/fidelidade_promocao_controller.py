"""Fidelidade, campanhas, cupons e documentos legais."""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from raizesdonordeste.security.autenticacao import publico, requer
from raizesdonordeste.service import documento_legal_service, fidelidade_service, promocao_service

fidelidade_bp = Blueprint("fidelidade", __name__)
campanhas_bp = Blueprint("campanhas", __name__)
cupons_bp = Blueprint("cupons", __name__)
documentos_bp = Blueprint("documentos_legais", __name__)


# ----------------------------------- Fidelidade --------------------------------------
@fidelidade_bp.get("/fidelidade/saldo")
@requer()
def consultar_saldo():
    """Consultar saldo de pontos

    O saldo pode ser devedor após estornos; nenhum ponto fica disponível até voltar a ser positivo.
    """
    return jsonify(fidelidade_service.saldo(g.usuario)), 200


@fidelidade_bp.get("/fidelidade/consentimento")
@requer()
def consultar_consentimento():
    """Consultar situação e versão do consentimento"""
    return jsonify(fidelidade_service.situacao_consentimento(g.usuario)), 200


@fidelidade_bp.post("/fidelidade/consentimento")
@requer()
def conceder_consentimento():
    """Consentir explicitamente com o uso de pontos

    Somente o próprio titular consente. Gera um evento imutável (finalidade, versão, data/hora e origem).
    """
    situacao, criado = fidelidade_service.consentir(g.usuario)
    return jsonify(situacao), (201 if criado else 200)


@fidelidade_bp.delete("/fidelidade/consentimento")
@requer()
def revogar_consentimento():
    """Revogar o consentimento"""
    fidelidade_service.revogar(g.usuario)
    return "", 204


# ------------------------------------ Campanhas --------------------------------------
@campanhas_bp.post("/campanhas")
@requer("ADMIN", "GERENTE")
def criar_campanha():
    """Criar campanha (desconto automático por produto)

    Rejeita períodos sobrepostos para o mesmo produto/escopo (409 CAMPANHA_PERIODO_SOBREPOSTO).
    GERENTE só cria campanhas da própria unidade.
    """
    return jsonify(promocao_service.criar_campanha(g.usuario)), 201


@campanhas_bp.get("/campanhas")
@requer("ADMIN", "GERENTE")
def listar_campanhas():
    """Listar campanhas (paginado, no escopo do usuário)"""
    return jsonify(promocao_service.listar_campanhas(g.usuario)), 200


@campanhas_bp.get("/campanhas/<int:campanha_id>")
@requer("ADMIN", "GERENTE")
def buscar_campanha(campanha_id):
    """Buscar campanha por ID"""
    return jsonify(promocao_service.buscar_campanha(g.usuario, campanha_id)), 200


@campanhas_bp.put("/campanhas/<int:campanha_id>")
@requer("ADMIN", "GERENTE")
def atualizar_campanha(campanha_id):
    """Atualizar campanha"""
    return jsonify(promocao_service.atualizar_campanha(g.usuario, campanha_id)), 200


@campanhas_bp.delete("/campanhas/<int:campanha_id>")
@requer("ADMIN", "GERENTE")
def desativar_campanha(campanha_id):
    """Desativar campanha (exclusão lógica)"""
    promocao_service.desativar_campanha(g.usuario, campanha_id)
    return "", 204


# -------------------------------------- Cupons ---------------------------------------
@cupons_bp.post("/cupons")
@requer("ADMIN", "GERENTE")
def criar_cupom():
    """Criar cupom

    ADMIN cria cupons globais ou locais; GERENTE somente cupom local da sua unidade.
    """
    return jsonify(promocao_service.criar_cupom(g.usuario)), 201


@cupons_bp.get("/cupons")
@requer("ADMIN", "GERENTE")
def listar_cupons():
    """Listar cupons (paginado, no escopo do usuário)"""
    return jsonify(promocao_service.listar_cupons(g.usuario)), 200


@cupons_bp.get("/cupons/<int:cupom_id>")
@requer("ADMIN", "GERENTE")
def buscar_cupom(cupom_id):
    """Buscar cupom por ID"""
    return jsonify(promocao_service.buscar_cupom(g.usuario, cupom_id)), 200


@cupons_bp.put("/cupons/<int:cupom_id>")
@requer("ADMIN", "GERENTE")
def atualizar_cupom(cupom_id):
    """Atualizar cupom"""
    return jsonify(promocao_service.atualizar_cupom(g.usuario, cupom_id)), 200


@cupons_bp.delete("/cupons/<int:cupom_id>")
@requer("ADMIN", "GERENTE")
def desativar_cupom(cupom_id):
    """Desativar cupom (exclusão lógica)"""
    promocao_service.desativar_cupom(g.usuario, cupom_id)
    return "", 204


# ------------------------------- Documentos legais -----------------------------------
@documentos_bp.get("/documentos-legais/termos-uso")
@publico
def consultar_termos_uso():
    """Consultar versão, hash SHA-256 e conteúdo dos termos vigentes"""
    return jsonify(documento_legal_service.consultar_termos()), 200


@documentos_bp.get("/documentos-legais/aviso-privacidade")
@publico
def consultar_aviso_privacidade():
    """Consultar o aviso de privacidade vigente"""
    return jsonify(documento_legal_service.consultar_aviso_privacidade()), 200


@documentos_bp.get("/documentos-legais/termos-uso/aceite")
@requer(exige_termos=False)
def consultar_aceite():
    """Consultar o aceite contratual do usuário"""
    return jsonify(documento_legal_service.consultar_aceite(g.usuario)), 200


@documentos_bp.put("/documentos-legais/termos-uso/aceite")
@requer(exige_termos=False)
def registrar_aceite():
    """Registrar (ou repetir de forma idempotente) o aceite da versão vigente

    Aceite contratual; não é revogável como o consentimento LGPD da fidelidade.
    """
    resultado, criado = documento_legal_service.aceitar(g.usuario)
    return jsonify(resultado), (201 if criado else 200)
