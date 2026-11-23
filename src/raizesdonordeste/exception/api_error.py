"""Exceção de domínio convertida pelo handler global no contrato de erro padrão."""
from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, erro: str, mensagem: str, detalhes: list[dict] | None = None):
        super().__init__(mensagem)
        self.status = status
        self.erro = erro
        self.mensagem = mensagem
        self.detalhes = detalhes or []


def nao_encontrado(recurso: str) -> ApiError:
    return ApiError(404, "RECURSO_NAO_ENCONTRADO", f"{recurso} não encontrado(a).")


def acesso_negado(mensagem: str = "Seu perfil não tem permissão para esta operação.") -> ApiError:
    return ApiError(403, "ACESSO_NEGADO", mensagem)


def conflito(codigo: str, mensagem: str, detalhes: list[dict] | None = None) -> ApiError:
    return ApiError(409, codigo, mensagem, detalhes)
