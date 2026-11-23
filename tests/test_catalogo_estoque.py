from conftest import CARNE, CUSCUZ, TAPIOCA


def test_listagem_publica_paginada_e_validada(api):
    r = api("GET", "/api/produtos?page=0&limit=2")
    corpo = r.get_json()
    assert r.status_code == 200 and len(corpo["content"]) == 2
    assert (corpo["totalElements"], corpo["totalPages"], corpo["limit"]) == (4, 2, 2)
    assert api("GET", "/api/produtos?limit=0").status_code == 422
    assert api("GET", "/api/produtos?page=abc").status_code == 422
    assert api("GET", "/api/produtos/1").get_json()["nome"] == "Tapioca"
    assert api("GET", "/api/produtos/999").status_code == 404


def test_disponibilidade_por_unidade(api):
    assert api("GET", "/api/produtos/unidade/1").status_code == 401
    itens = api("GET", "/api/produtos/unidade/1", "cliente").get_json()["content"]
    assert len(itens) == 4 and all(i["disponivel"] and i["quantidadeDisponivel"] == 50 for i in itens)
    assert api("GET", "/api/produtos/unidade/99", "cliente").status_code == 404


def test_gerente_gerencia_produtos_cliente_nao(api):
    corpo = {"nome": "Baião de Dois", "categoria": "pratos", "precoCentavos": 2800}
    assert api("POST", "/api/produtos", "cliente", corpo).status_code == 403
    criado = api("POST", "/api/produtos", "gerente", corpo)
    assert criado.status_code == 201
    pid = criado.get_json()["id"]
    assert api("PUT", f"/api/produtos/{pid}", "gerente", {**corpo, "precoCentavos": 3000}).get_json()["precoCentavos"] == 3000
    assert api("DELETE", f"/api/produtos/{pid}", "admin").status_code == 204
    assert api("GET", f"/api/produtos/{pid}").status_code == 404
    assert api("POST", "/api/produtos", "admin", {"nome": "X"}).status_code == 422


def test_crud_de_unidades(api):
    assert api("POST", "/api/unidades", "admin", {"nome": "Unidade Boa Viagem", "cidade": "Recife"}).status_code == 201
    assert api("GET", "/api/unidades", "cliente").get_json()["totalElements"] == 3
    assert api("PUT", "/api/unidades/3", "admin", {"nome": "Boa Viagem", "cidade": "Recife"}).get_json()["nome"] == "Boa Viagem"
    assert api("DELETE", "/api/unidades/3", "admin").status_code == 204
    assert api("GET", "/api/unidades", "cliente").get_json()["totalElements"] == 2
    assert api("GET", "/api/unidades/3", "cliente").get_json()["ativa"] is False
    assert api("POST", "/api/pedidos", "cliente", {"unidadeId": 3, "canalPedido": "APP",
                                                     "itens": [{"produtoId": 1, "quantidade": 1}]}).status_code == 404


def test_movimentacoes_auditaveis_e_pseudonimizadas(api):
    entrada = api("POST", "/api/estoque/1/movimentacoes", "gerente",
                  {"tipo": "ENTRADA", "quantidade": 10, "motivo": "Reposição fornecedor"})
    assert entrada.status_code == 201
    mov = entrada.get_json()
    assert (mov["saldoAnterior"], mov["saldoPosterior"]) == (50, 60)
    assert mov["responsavel"].startswith("u_") and "gerente" not in mov["responsavel"]
    saida = api("POST", "/api/estoque/1/movimentacoes", "gerente",
                {"tipo": "SAIDA", "quantidade": 5, "motivo": "Perda por validade"})
    assert saida.get_json()["saldoPosterior"] == 55
    hist = api("GET", "/api/estoque/1/movimentacoes", "gerente").get_json()
    assert hist["totalElements"] == 2 and hist["content"][0]["tipo"] == "SAIDA"


def test_saida_nunca_deixa_saldo_negativo(api):
    r = api("POST", "/api/estoque/1/movimentacoes", "gerente",
            {"tipo": "SAIDA", "quantidade": 51, "motivo": "Teste de limite"})
    assert (r.status_code, r.get_json()["error"]) == (409, "ESTOQUE_INSUFICIENTE")
    assert api.estoque(1) == 50


def test_gerente_so_acessa_estoque_da_propria_unidade(api):
    assert api("GET", "/api/estoque/5", "gerente").status_code == 403      # unidade 2
    assert api("GET", "/api/estoque/unidade/2", "gerente").status_code == 403
    assert api("POST", "/api/estoque/5/movimentacoes", "gerente",
               {"tipo": "ENTRADA", "quantidade": 1, "motivo": "Indevido"}).status_code == 403
    assert api("GET", "/api/estoque/5", "admin").status_code == 200
    assert api("GET", "/api/estoque/1", "cozinha").status_code == 403
    assert api("GET", "/api/estoque/unidade/1", "gerente").get_json()["totalElements"] == 4


def test_atualizar_quantidade_gera_movimentacao_de_ajuste(api):
    r = api("PUT", "/api/estoque/1", "gerente", {"quantidade": 20})
    assert r.get_json()["quantidade"] == 20
    ultimo = api("GET", "/api/estoque/1/movimentacoes", "gerente").get_json()["content"][0]
    assert (ultimo["tipo"], ultimo["quantidade"], ultimo["motivo"]) == ("SAIDA", 30, "AJUSTE_DE_ESTOQUE")


def test_item_sem_saldo_fica_indisponivel_e_nao_vende(api):
    api("PUT", f"/api/estoque/{CARNE}", "gerente", {"quantidade": 0})
    itens = {i["id"]: i for i in api("GET", "/api/produtos/unidade/1", "cliente").get_json()["content"]}
    assert itens[CARNE]["disponivel"] is False and itens[TAPIOCA]["disponivel"] is True
    r = api.pedido([(CARNE, 1)])
    assert (r.status_code, r.get_json()["error"]) == (409, "ESTOQUE_INSUFICIENTE")
    api("POST", f"/api/estoque/{CARNE}/movimentacoes", "gerente", {"tipo": "ENTRADA", "quantidade": 2, "motivo": "Reposição"})
    assert api.pedido([(CARNE, 1)]).status_code == 201


def test_remover_e_recriar_estoque(api):
    assert api("DELETE", f"/api/estoque/{CUSCUZ}", "gerente").status_code == 204
    cardapio = api("GET", "/api/produtos/unidade/1", "cliente").get_json()["content"]
    assert CUSCUZ not in [i["id"] for i in cardapio]
    r = api.pedido([(CUSCUZ, 1)])
    assert (r.status_code, r.get_json()["error"]) == (409, "PRODUTO_INDISPONIVEL")
    novo = api("POST", "/api/estoque", "gerente", {"unidadeId": 1, "produtoId": CUSCUZ, "quantidade": 7})
    assert novo.status_code == 201 and novo.get_json()["quantidade"] >= 7
    assert api("POST", "/api/estoque", "gerente", {"unidadeId": 1, "produtoId": CUSCUZ, "quantidade": 1}).status_code == 409
    historico = api("GET", f"/api/estoque/{CUSCUZ}/movimentacoes", "gerente").get_json()
    assert historico["totalElements"] >= 1                      # trilha preservada após a remoção lógica
