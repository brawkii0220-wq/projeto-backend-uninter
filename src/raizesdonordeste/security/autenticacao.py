"""Autenticação JWT e controle de acesso por perfil (RBAC).

`@requer(*perfis)` exige token válido (e, por padrão, aceite dos termos vigentes).
`@publico` marca rotas abertas. Ambos anotam a função para a geração do OpenAPI.
"""
from __future__ import annotations

from functools import wraps

import jwt
from flask import current_app, g, request

from raizesdonordeste.exception.api_error import ApiError, acesso_negado
from raizesdonordeste.repository.database import conexao
from raizesdonordeste.security import jwt_service
from raizesdonordeste.service import documento_legal_service


def _autenticar():
    cabecalho = request.headers.get("Authorization", "")
    if not cabecalho.startswith("Bearer ") or len(cabecalho) <= 7:
        raise ApiError(401, "NAO_AUTENTICADO", "Token de acesso ausente.")
    try:
        usuario_id = jwt_service.validar(current_app.extensions["settings"], cabecalho[7:])
    except (jwt.PyJWTError, ValueError):
        raise ApiError(401, "TOKEN_INVALIDO", "Token inválido ou expirado.")
    usuario = conexao().execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    if usuario is None or not usuario["ativo"] or usuario["anonimizado"]:
        raise ApiError(401, "TOKEN_INVALIDO", "Usuário inexistente ou desativado.")
    return usuario


def requer(*perfis: str, exige_termos: bool = True):
    def decorador(funcao):
        @wraps(funcao)
        def envoltorio(*args, **kwargs):
            usuario = _autenticar()
            if perfis and usuario["perfil"] not in perfis:
                raise acesso_negado()
            if exige_termos and not documento_legal_service.aceite_vigente(conexao(), usuario["id"]):
                raise ApiError(409, "TERMOS_USO_NAO_ACEITOS",
                               "É necessário aceitar a versão vigente dos termos de uso para continuar.",
                               [{"field": "termosUso", "issue": "use PUT /documentos-legais/termos-uso/aceite"}])
            g.usuario = usuario
            return funcao(*args, **kwargs)
        envoltorio._openapi = {"publico": False, "perfis": list(perfis), "termos": exige_termos}
        return envoltorio
    return decorador


def publico(funcao):
    funcao._openapi = {"publico": True, "perfis": [], "termos": False}
    return funcao
