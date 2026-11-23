import os
import tempfile

import pytest

from raizesdonordeste import Settings, create_app

SENHAS = {"cliente": "cliente123", "cozinha": "cozinha123", "atendente": "atendente123",
          "gerente": "gerente123", "admin": "admin123"}

# Ids do seed: unidades 1 (Centro) e 2 (Zona Sul); produtos 1 Tapioca (R$12), 2 Cuscuz (R$10),
# 3 Suco de Cajá (R$8), 4 Carne de Sol (R$35); estoques 1-4 = unidade 1, 5-8 = unidade 2 (50 un. cada).
TAPIOCA, CUSCUZ, SUCO, CARNE = 1, 2, 3, 4


def configuracao(**extra) -> Settings:
    base = dict(db_path=os.path.join(tempfile.mkdtemp(), "teste.db"), senha_iteracoes=1000,
                pagamento_forcar_status="APROVADO", pagamento_forcar_status_estorno="CONFIRMADO")
    base.update(extra)
    return Settings.carregar(env={}, **base)


@pytest.fixture()
def app():
    return create_app(configuracao())


@pytest.fixture()
def client(app):
    return app.test_client()


def chamar(client, metodo, url, token=None, json=None, headers=None):
    cabecalhos = dict(headers or {})
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    return client.open(url, method=metodo, json=json, headers=cabecalhos)


@pytest.fixture()
def tokens(client):
    resultado = {}
    for perfil, senha in SENHAS.items():
        r = client.post("/api/auth/login", json={"email": f"{perfil}@raizes.com", "senha": senha})
        assert r.status_code == 200, r.get_json()
        resultado[perfil] = r.get_json()["token"]
    return resultado


@pytest.fixture()
def api(client, tokens):
    class Api:
        c = client
        t = tokens

        def __call__(self, metodo, url, perfil=None, json=None, headers=None, token=None):
            return chamar(client, metodo, url, token or (tokens[perfil] if perfil else None), json, headers)

        def pedido(self, itens, perfil="cliente", unidade=1, canal="APP", **extra):
            corpo = {"unidadeId": unidade, "canalPedido": canal,
                     "itens": [{"produtoId": p, "quantidade": q} for p, q in itens]}
            corpo.update(extra)
            return self("POST", "/api/pedidos", perfil, corpo)

        def pagar(self, pedido_id, perfil="cliente", forma="PIX", forcar=None):
            cab = {"X-Forcar-Status-Pagamento": forcar} if forcar else None
            return self("POST", f"/api/pedidos/{pedido_id}/pagamento", perfil, {"formaPagamento": forma}, cab)

        def pedido_pago(self, itens, **extra):
            r = self.pedido(itens, **extra)
            assert r.status_code == 201, r.get_json()
            pid = r.get_json()["id"]
            assert self.pagar(pid).status_code == 201
            return pid

        def status(self, pedido_id, novo, perfil):
            return self("PATCH", f"/api/pedidos/{pedido_id}/status", perfil, {"status": novo})

        def estoque(self, estoque_id):
            return self("GET", f"/api/estoque/{estoque_id}", "admin").get_json()["quantidade"]

        def saldo(self, perfil="cliente"):
            return self("GET", "/api/fidelidade/saldo", perfil).get_json()

    return Api()
