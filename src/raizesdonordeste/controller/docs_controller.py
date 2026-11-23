"""Documentação interativa (Swagger UI) — registrada apenas fora do perfil prod."""
from __future__ import annotations

import json

import yaml
from flask import Blueprint, Response, current_app, jsonify

from raizesdonordeste.config import openapi
from raizesdonordeste.config.settings import CONTEXT_PATH

docs_bp = Blueprint("docs", __name__)

_PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Raízes do Nordeste - Swagger</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.11.0/swagger-ui.min.css"></head>
<body><div id="swagger-ui"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.11.0/swagger-ui-bundle.min.js"></script>
<script>window.ui = SwaggerUIBundle({url: "%s/v3/api-docs", dom_id: "#swagger-ui"});</script></body></html>"""


def _spec() -> dict:
    app = current_app._get_current_object()
    if "openapi" not in app.extensions:
        app.extensions["openapi"] = openapi.gerar(app)
    return app.extensions["openapi"]


@docs_bp.get("/v3/api-docs")
def api_docs_json():
    return jsonify(_spec())


@docs_bp.get("/v3/api-docs.yaml")
def api_docs_yaml():
    return Response(yaml.safe_dump(json.loads(json.dumps(_spec())), allow_unicode=True, sort_keys=False),
                    mimetype="application/yaml")


@docs_bp.get("/swagger-ui.html")
def swagger_ui():
    return Response(_PAGINA % CONTEXT_PATH, mimetype="text/html")
