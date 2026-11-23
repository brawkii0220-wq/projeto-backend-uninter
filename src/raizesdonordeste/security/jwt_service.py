"""Emissão e validação de tokens JWT (HS256)."""
from __future__ import annotations

from datetime import timedelta

import jwt

from raizesdonordeste.config.settings import Settings
from raizesdonordeste.util.tempo import agora


def emitir(settings: Settings, usuario) -> tuple[str, int]:
    agora_utc = agora()
    expira_em = settings.jwt_expiration_minutes * 60
    token = jwt.encode(
        {"sub": str(usuario["id"]), "perfil": usuario["perfil"], "iat": agora_utc,
         "exp": agora_utc + timedelta(seconds=expira_em)},
        settings.jwt_secret, algorithm="HS256")
    return token, expira_em


def validar(settings: Settings, token: str) -> int:
    """Devolve o id do usuário ou levanta jwt.PyJWTError."""
    claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    return int(claims["sub"])
