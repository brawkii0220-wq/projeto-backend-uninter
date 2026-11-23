from __future__ import annotations

import logging

from flask import current_app

from raizesdonordeste.dto.validacao import Validador, corpo_json
from raizesdonordeste.exception.api_error import ApiError
from raizesdonordeste.repository import usuario_repository
from raizesdonordeste.repository.database import conexao
from raizesdonordeste.security import jwt_service, senhas
from raizesdonordeste.util.pseudonimizacao import pseudonimizar

logger = logging.getLogger("raizes.auth")
_hash_ficticio: str | None = None


def login() -> dict:
    corpo = corpo_json()
    v = Validador(corpo)
    email = v.texto("email", maximo=150)
    senha = v.texto("senha", maximo=100, aparar=False)
    v.verificar()

    settings = current_app.extensions["settings"]
    usuario = usuario_repository.buscar_por_email(conexao(), email)
    global _hash_ficticio
    if _hash_ficticio is None:  # mantém o tempo de resposta parecido quando o e-mail não existe
        _hash_ficticio = senhas.gerar_hash("senha-ficticia", settings.senha_iteracoes)
    senha_ok = senhas.verificar(senha, usuario["senha_hash"] if usuario else _hash_ficticio)
    if usuario is None or not senha_ok or not usuario["ativo"] or usuario["anonimizado"]:
        logger.warning("Falha de login para %s", pseudonimizar(email))
        raise ApiError(401, "CREDENCIAIS_INVALIDAS", "E-mail ou senha incorretos.")
    token, expira_em = jwt_service.emitir(settings, usuario)
    logger.info("Login realizado por %s (%s)", pseudonimizar(email), usuario["perfil"])
    return {"token": token, "tipo": "Bearer", "expiraEmSegundos": expira_em}
