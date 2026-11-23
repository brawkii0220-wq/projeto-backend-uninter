"""Tratamento global de erros: todas as falhas seguem o mesmo contrato JSON."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from raizesdonordeste.config.request_context import request_id_atual
from raizesdonordeste.exception.api_error import ApiError
from raizesdonordeste.util.tempo import agora_iso

logger = logging.getLogger("raizes.erros")

_CODIGOS_HTTP = {
    400: "REQUISICAO_INVALIDA", 401: "NAO_AUTENTICADO", 403: "ACESSO_NEGADO",
    404: "RECURSO_NAO_ENCONTRADO", 405: "METODO_NAO_PERMITIDO", 415: "TIPO_MIDIA_NAO_SUPORTADO",
}


_MENSAGENS_HTTP = {
    400: "Requisição inválida.", 401: "Autenticação necessária.", 403: "Acesso negado.",
    404: "Recurso não encontrado.", 405: "Método HTTP não permitido para este recurso.",
    413: "Corpo da requisição grande demais.", 415: "Tipo de mídia não suportado. Use application/json.",
}


def resposta_erro(status: int, erro: str, mensagem: str, detalhes: list[dict] | None = None):
    corpo = {
        "error": erro,
        "message": mensagem,
        "details": detalhes or [],
        "timestamp": agora_iso(),
        "path": request.path,
        "requestId": request_id_atual(),
    }
    return jsonify(corpo), status


def registrar(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return resposta_erro(e.status, e.erro, e.mensagem, e.detalhes)

    @app.errorhandler(HTTPException)
    def _http(e: HTTPException):
        codigo = _CODIGOS_HTTP.get(e.code or 500, "ERRO_HTTP")
        # Mensagens padronizadas em português (a descrição do Werkzeug é em inglês e pode expor detalhes).
        return resposta_erro(e.code or 500, codigo, _MENSAGENS_HTTP.get(e.code or 500, e.name))

    @app.errorhandler(Exception)
    def _inesperado(e: Exception):
        logger.exception("Erro inesperado")
        return resposta_erro(500, "ERRO_INTERNO", "Erro interno inesperado.")
