"""Correlação de requisições (X-Request-ID) e logs estruturados."""
from __future__ import annotations

import contextvars
import logging
import re
import uuid

from flask import Flask, g, request

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:\-]{8,100}$")
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
logger = logging.getLogger("raizes.http")


def request_id_atual() -> str:
    return _request_id_var.get()


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_atual()
        return True


def configurar_logging(nivel: int = logging.INFO) -> None:
    raiz = logging.getLogger("raizes")
    if any(isinstance(f, RequestIdFilter) for h in raiz.handlers for f in h.filters):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(request_id)s] %(name)s - %(message)s"))
    handler.addFilter(RequestIdFilter())
    raiz.addHandler(handler)
    raiz.setLevel(nivel)
    raiz.propagate = False


def registrar(app: Flask) -> None:
    @app.before_request
    def _iniciar():
        recebido = request.headers.get("X-Request-ID", "")
        rid = recebido if _REQUEST_ID_RE.match(recebido) else str(uuid.uuid4())
        g.request_id = rid
        g._rid_token = _request_id_var.set(rid)

    @app.after_request
    def _finalizar(resposta):
        resposta.headers["X-Request-ID"] = g.get("request_id", request_id_atual())
        logger.info("%s %s -> %s", request.method, request.path, resposta.status_code)
        return resposta

    @app.teardown_request
    def _limpar(_exc):
        token = g.pop("_rid_token", None)
        if token is not None:
            _request_id_var.reset(token)
