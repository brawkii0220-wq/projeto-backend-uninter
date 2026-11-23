"""CORS configurável por origem (sem dependências externas)."""
from __future__ import annotations

from flask import Flask, request

from raizesdonordeste.config.settings import Settings


def registrar(app: Flask, settings: Settings) -> None:
    @app.after_request
    def _cors(resposta):
        origem = request.headers.get("Origin")
        if not origem or origem not in settings.cors_allowed_origins:
            return resposta
        resposta.headers["Access-Control-Allow-Origin"] = origem
        resposta.headers.add("Vary", "Origin")
        resposta.headers["Access-Control-Expose-Headers"] = "X-Request-ID, Idempotency-Replayed"
        if settings.cors_allow_credentials:
            resposta.headers["Access-Control-Allow-Credentials"] = "true"
        if request.method == "OPTIONS" and request.headers.get("Access-Control-Request-Method"):
            resposta.headers["Access-Control-Allow-Methods"] = ", ".join(settings.cors_allowed_methods)
            if "*" in settings.cors_allowed_headers:
                pedidos = request.headers.get("Access-Control-Request-Headers", "")
                if pedidos:
                    resposta.headers["Access-Control-Allow-Headers"] = pedidos
            else:
                resposta.headers["Access-Control-Allow-Headers"] = ", ".join(settings.cors_allowed_headers)
            resposta.headers["Access-Control-Max-Age"] = "3600"
        return resposta
