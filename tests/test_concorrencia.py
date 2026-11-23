"""Concorrência: estoque, cupons, campanhas e cancelamentos disputados em paralelo.

Cada thread usa seu próprio test client (e, portanto, sua própria conexão SQLite). O BEGIN IMMEDIATE das
transações serializa as escritas, então exatamente uma das requisições concorrentes pode vencer.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

from conftest import CARNE, CUSCUZ, SUCO
from test_campanhas_cupons import campanha


def em_paralelo(app, tarefas):
    """Executa cada tarefa(client) em uma thread, largando todas ao mesmo tempo."""
    largada = threading.Barrier(len(tarefas))

    def executar(tarefa):
        cliente = app.test_client()
        largada.wait(timeout=10)
        return tarefa(cliente)

    with ThreadPoolExecutor(max_workers=len(tarefas)) as pool:
        return [f.result(timeout=60) for f in [pool.submit(executar, t) for t in tarefas]]


def requisicao(api, perfil, metodo, url, json=None):
    token = api.t[perfil]

    def tarefa(cliente):
        return cliente.open(url, method=metodo, json=json, headers={"Authorization": f"Bearer {token}"})
    return tarefa


def test_ultima_unidade_do_estoque_so_pode_ser_vendida_uma_vez(app, api):
    assert api("PUT", "/api/estoque/4", "admin", {"quantidade": 1}).status_code == 200        # Carne de Sol, unidade 1
    corpo = {"unidadeId": 1, "canalPedido": "APP", "itens": [{"produtoId": CARNE, "quantidade": 1}]}
    respostas = em_paralelo(app, [requisicao(api, "cliente", "POST", "/api/pedidos", corpo) for _ in range(4)])
    codigos = sorted(r.status_code for r in respostas)
    assert codigos == [201, 409, 409, 409]
    assert {r.get_json()["error"] for r in respostas if r.status_code == 409} == {"ESTOQUE_INSUFICIENTE"}
    assert api.estoque(4) == 0                                              # nunca negativo


def test_cupom_com_limite_de_uso_unico_vale_para_um_pedido(app, api):
    api("POST", "/api/cupons", "admin", {"codigo": "UNICO", "tipo": "VALOR_FIXO", "valor": 100, "limiteUso": 1})
    corpo = {"unidadeId": 1, "canalPedido": "WEB", "cupomCodigo": "UNICO",
             "itens": [{"produtoId": CUSCUZ, "quantidade": 1}]}
    respostas = em_paralelo(app, [requisicao(api, "cliente", "POST", "/api/pedidos", corpo) for _ in range(4)])
    assert sorted(r.status_code for r in respostas) == [201, 409, 409, 409]
    cupom = next(c for c in api("GET", "/api/cupons", "admin").get_json()["content"] if c["codigo"] == "UNICO")
    assert cupom["usos"] == 1
    assert api.estoque(2) == 49                                             # os pedidos rejeitados não reservaram nada


def test_campanhas_sobrepostas_criadas_ao_mesmo_tempo_geram_apenas_uma(app, api):
    corpo = campanha(produto=SUCO, dias=None)
    respostas = em_paralelo(app, [requisicao(api, "gerente", "POST", "/api/campanhas", corpo) for _ in range(4)])
    assert sorted(r.status_code for r in respostas) == [201, 409, 409, 409]
    assert {r.get_json()["error"] for r in respostas if r.status_code == 409} == {"CAMPANHA_PERIODO_SOBREPOSTO"}
    ativas = [c for c in api("GET", "/api/campanhas", "gerente").get_json()["content"] if c["ativa"]]
    assert len(ativas) == 1


def test_cancelamentos_concorrentes_estornam_e_devolvem_estoque_uma_unica_vez(app, api):
    pid = api.pedido_pago([(CUSCUZ, 3)])
    assert api.estoque(2) == 47
    respostas = em_paralelo(app, [requisicao(api, "cliente", "POST", f"/api/pedidos/{pid}/cancelamento")
                                  for _ in range(4)])
    assert sorted(r.status_code for r in respostas) == [200, 409, 409, 409]
    assert {r.get_json()["error"] for r in respostas if r.status_code == 409} == {"PEDIDO_NAO_CANCELAVEL"}
    tentativas = api("GET", f"/api/pedidos/{pid}/pagamento/tentativas", "cliente").get_json()
    assert [t["tipo"] for t in tentativas].count("ESTORNO") == 1            # um único estorno solicitado
    assert api.estoque(2) == 50                                             # devolvido uma única vez
    movimentos = api("GET", "/api/estoque/2/movimentacoes", "admin").get_json()["content"]
    assert [m["motivo"] for m in movimentos].count("DEVOLUCAO_CANCELAMENTO") == 1


def test_pagamentos_simultaneos_do_mesmo_pedido_aprovam_apenas_uma_vez(app, api):
    api.pedido([(CUSCUZ, 1)], perfil="cliente")
    pid = api("GET", "/api/pedidos", "cliente").get_json()["content"][0]["id"]
    respostas = em_paralelo(app, [requisicao(api, "cliente", "POST", f"/api/pedidos/{pid}/pagamento",
                                             {"formaPagamento": "PIX"}) for _ in range(4)])
    assert sorted(r.status_code for r in respostas) == [201, 409, 409, 409]
    tentativas = api("GET", f"/api/pedidos/{pid}/pagamento/tentativas", "cliente").get_json()
    assert [t["status"] for t in tentativas] == ["APROVADO"]
