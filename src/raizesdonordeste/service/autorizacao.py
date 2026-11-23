"""Regras de escopo por unidade, compartilhadas pelos services."""
from __future__ import annotations

from raizesdonordeste.exception.api_error import acesso_negado


def exigir_gestao_unidade(usuario, unidade_id: int) -> None:
    """ADMIN em qualquer unidade; GERENTE somente na sua."""
    if usuario["perfil"] == "ADMIN":
        return
    if usuario["perfil"] == "GERENTE" and usuario["unidade_id"] == unidade_id:
        return
    raise acesso_negado("Você não tem acesso à gestão desta unidade.")


def opera_na_unidade(usuario, unidade_id: int) -> bool:
    """Equipe (cozinha, atendente, gerente) só opera na própria unidade; ADMIN em todas."""
    if usuario["perfil"] == "ADMIN":
        return True
    return usuario["perfil"] in ("COZINHA", "ATENDENTE", "GERENTE") and usuario["unidade_id"] == unidade_id
