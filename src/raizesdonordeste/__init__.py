"""API REST "Raízes do Nordeste" — pedidos multicanal, estoque, fidelidade, campanhas e pagamento simulado."""
from __future__ import annotations

from flask import Flask

from raizesdonordeste.config import cors, request_context
from raizesdonordeste.config.settings import CONTEXT_PATH, Settings
from raizesdonordeste.exception import handlers
from raizesdonordeste.gateway.gateway_pagamento import GatewayPagamentoSimulado
from raizesdonordeste.repository import database
from raizesdonordeste.service import documento_legal_service

__all__ = ["create_app", "Settings"]


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.carregar()
    app = Flask(__name__)
    app.extensions["settings"] = settings
    app.url_map.strict_slashes = False
    app.json.sort_keys = False
    app.json.ensure_ascii = False

    request_context.configurar_logging()
    request_context.registrar(app)
    cors.registrar(app, settings)
    handlers.registrar(app)
    app.teardown_appcontext(database.fechar_conexao)

    app.extensions["gateway"] = GatewayPagamentoSimulado(settings.pagamento_forcar_status,
                                                         settings.pagamento_forcar_status_estorno)
    app.extensions["documentos"] = documento_legal_service.carregar(settings)

    from raizesdonordeste.controller.auth_usuario_controller import auth_bp, usuarios_bp
    from raizesdonordeste.controller.catalogo_controller import estoque_bp, produtos_bp, unidades_bp
    from raizesdonordeste.controller.docs_controller import docs_bp
    from raizesdonordeste.controller.fidelidade_promocao_controller import (campanhas_bp, cupons_bp,
                                                                            documentos_bp, fidelidade_bp)
    from raizesdonordeste.controller.pedido_controller import pagamento_bp, pedidos_bp

    for bp in (auth_bp, usuarios_bp, unidades_bp, produtos_bp, estoque_bp, pedidos_bp, pagamento_bp,
               fidelidade_bp, campanhas_bp, cupons_bp, documentos_bp):
        app.register_blueprint(bp, url_prefix=CONTEXT_PATH)
    if settings.docs_enabled:
        app.register_blueprint(docs_bp, url_prefix=CONTEXT_PATH)

    @app.cli.command("db-migrar")
    def _db_migrar():
        """Aplica as migrations pendentes (também executado na inicialização)."""
        print("Migrations aplicadas:", database.migrar(database.conexao()) or "nenhuma pendente")

    @app.cli.command("db-limpar")
    def _db_limpar():
        """Apaga todo o banco (equivalente ao flyway clean). Bloqueado no perfil prod."""
        print("Objetos removidos:", database.limpar(database.conexao(), settings.profile))

    with app.app_context():
        database.migrar(database.conexao())
        if settings.seed_enabled:
            from raizesdonordeste.config import seed
            seed.popular(settings)
    return app
