"""Origem informativa da requisição (usada nas trilhas de aceite e consentimento)."""
from __future__ import annotations

from flask import has_request_context, request


def origem_requisicao() -> str:
    if not has_request_context():
        return "SEED"
    return (request.headers.get("Origin") or "API")[:100]
