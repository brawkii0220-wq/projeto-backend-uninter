"""Autenticação e usuários."""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from raizesdonordeste.security.autenticacao import publico, requer
from raizesdonordeste.service import autenticacao_service, usuario_service

auth_bp = Blueprint("autenticacao", __name__)
usuarios_bp = Blueprint("usuarios", __name__)


@auth_bp.post("/auth/login")
@publico
def login():
    """Autenticar e obter token JWT

    Informe `email` e `senha`. O token expira conforme `JWT_EXPIRATION_MINUTES` (padrão 60).
    """
    return jsonify(autenticacao_service.login()), 200


@usuarios_bp.post("/usuarios")
@publico
def registrar_usuario():
    """Registrar cliente com aceite dos termos vigentes

    Exige `aceiteTermosUso: true`, `versaoTermosUso` e `hashTermosUso` (consulte GET /documentos-legais/termos-uso).
    """
    return jsonify(usuario_service.registrar()), 201


@usuarios_bp.get("/usuarios")
@requer("ADMIN")
def listar_usuarios():
    """Listar usuários (paginado)"""
    return jsonify(usuario_service.listar()), 200


@usuarios_bp.get("/usuarios/<int:usuario_id>")
@requer("ADMIN")
def buscar_usuario(usuario_id):
    """Buscar usuário por ID"""
    return jsonify(usuario_service.buscar(usuario_id)), 200


@usuarios_bp.put("/usuarios/<int:usuario_id>")
@requer()
def atualizar_usuario(usuario_id):
    """Atualizar usuário; alteração de perfil/unidade somente por ADMIN

    Permitido ao próprio usuário ou a ADMIN.
    """
    return jsonify(usuario_service.atualizar(g.usuario, usuario_id)), 200


@usuarios_bp.delete("/usuarios/<int:usuario_id>")
@requer()
def anonimizar_usuario(usuario_id):
    """Anonimizar usuário (LGPD)

    Permitido ao próprio usuário ou a ADMIN. Pedidos e trilhas financeiras são preservados sem dados pessoais.
    """
    usuario_service.anonimizar(g.usuario, usuario_id)
    return "", 204
