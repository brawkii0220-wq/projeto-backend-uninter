"""Fidelidade: consentimento versionado e imutável, acúmulo, resgate, limites e saldo devedor."""
import dataclasses
import sqlite3

import pytest

from conftest import CARNE, CUSCUZ, SUCO


def consentir(api, perfil="cliente"):
    r = api("POST", "/api/fidelidade/consentimento", perfil)
    assert r.status_code in (200, 201), r.get_json()
    return r


def ganhar_pontos(api, itens=((CARNE, 2),)):
    """Cliente consente, paga e fica com pontos (1 ponto por R$ 1,00 pago)."""
    consentir(api)
    return api.pedido_pago(list(itens))


# ------------------------------------- consentimento -----------------------------------
def test_consentimento_concessao_idempotente_e_revogacao(api):
    inicial = api("GET", "/api/fidelidade/consentimento", "cliente").get_json()
    assert inicial["consentimentoAtivo"] is False and inicial["ultimoEvento"] is None
    assert inicial["finalidade"] == "FIDELIDADE_PONTOS" and inicial["versaoVigente"] == "1.0"

    primeiro = api("POST", "/api/fidelidade/consentimento", "cliente")
    assert primeiro.status_code == 201 and primeiro.get_json()["consentimentoAtivo"] is True
    assert primeiro.get_json()["ultimoEvento"]["tipo"] == "CONCESSAO"
    assert api("POST", "/api/fidelidade/consentimento", "cliente").status_code == 200      # repetir é seguro

    assert api("DELETE", "/api/fidelidade/consentimento", "cliente").status_code == 204
    revogado = api("GET", "/api/fidelidade/consentimento", "cliente").get_json()
    assert revogado["consentimentoAtivo"] is False and revogado["ultimoEvento"]["tipo"] == "REVOGACAO"
    assert api("DELETE", "/api/fidelidade/consentimento", "cliente").status_code == 204    # idempotente


def test_consentimento_exige_autenticacao_e_e_individual(api):
    assert api("GET", "/api/fidelidade/consentimento").status_code == 401
    consentir(api, "atendente")           # funcionário só registra o PRÓPRIO consentimento
    assert api("GET", "/api/fidelidade/consentimento", "cliente").get_json()["consentimentoAtivo"] is False
    assert api("GET", "/api/fidelidade/consentimento", "atendente").get_json()["consentimentoAtivo"] is True


def test_eventos_de_consentimento_sao_imutaveis(app, api):
    consentir(api)
    api("DELETE", "/api/fidelidade/consentimento", "cliente")
    conn = sqlite3.connect(app.extensions["settings"].db_path)
    assert conn.execute("SELECT COUNT(*) FROM consentimentos_fidelidade").fetchone()[0] == 2   # concessão + revogação
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE consentimentos_fidelidade SET tipo='CONCESSAO'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM consentimentos_fidelidade")
    conn.close()


def test_nova_versao_do_termo_exige_novo_consentimento(app, api):
    consentir(api)
    assert api.saldo()["consentimentoAtivo"] is True
    app.extensions["settings"] = dataclasses.replace(app.extensions["settings"], termo_fidelidade_versao="2.0")
    atual = api("GET", "/api/fidelidade/consentimento", "cliente").get_json()
    assert atual["consentimentoAtivo"] is False and atual["versaoVigente"] == "2.0"
    assert atual["ultimoEvento"]["versao"] == "1.0"
    assert api.pedido([(CUSCUZ, 1)], pontosResgatar=1).status_code == 403          # consentimento desatualizado
    assert consentir(api).get_json()["ultimoEvento"]["versao"] == "2.0"
    assert api.saldo()["consentimentoAtivo"] is True


# --------------------------------------- acúmulo ----------------------------------------
def test_pontos_so_sao_concedidos_com_consentimento(api):
    api.pedido_pago([(CARNE, 1)])                                       # R$ 35 sem consentimento
    assert api.saldo()["saldo"] == 0
    ganhar_pontos(api, [(CARNE, 1)])
    saldo = api.saldo()
    assert saldo["saldo"] == 35 and saldo["pontosDisponiveis"] == 35 and saldo["saldoDevedor"] is False


def test_pontos_sao_creditados_na_aprovacao_do_pagamento_e_nao_na_recusa(api):
    consentir(api)
    pid = api.pedido([(CARNE, 1)]).get_json()["id"]
    assert api.saldo()["saldo"] == 0
    recusado = api.pagar(pid, forcar="RECUSADO").get_json()
    assert recusado["pontosConcedidos"] == 0 and api.saldo()["saldo"] == 0
    aprovado = api.pagar(pid, forcar="APROVADO").get_json()
    assert aprovado["pontosConcedidos"] == 35 and api.saldo()["saldo"] == 35
    assert api("GET", f"/api/pedidos/{pid}", "cliente").get_json()["pontosConcedidos"] == 35


# ---------------------------------------- resgate ---------------------------------------
def test_resgate_exige_consentimento(api):
    r = api.pedido([(CUSCUZ, 1)], pontosResgatar=10)
    assert (r.status_code, r.get_json()["error"]) == (403, "CONSENTIMENTO_FIDELIDADE_NECESSARIO")


def test_resgate_reduz_total_e_debita_pontos(api):
    ganhar_pontos(api, [(CARNE, 2)])                                    # 70 pontos
    p = api.pedido([(CARNE, 1)], pontosResgatar=20).get_json()          # 20 pts = R$ 1,00
    assert (p["descontoPontosCentavos"], p["pontosResgatados"], p["totalCentavos"]) == (100, 20, 3400)
    assert api.saldo()["saldo"] == 50


def test_resgate_respeita_saldo_e_limite_de_50_por_cento(api):
    ganhar_pontos(api, [(CARNE, 3)])                                    # 105 pontos
    r = api.pedido([(CUSCUZ, 1)], pontosResgatar=106)
    assert (r.status_code, r.get_json()["error"]) == (409, "PONTOS_INSUFICIENTES")
    assert r.get_json()["details"][0]["issue"] == "Disponível: 105"
    r = api.pedido([(SUCO, 1)], pontosResgatar=81)                      # R$ 8: 50% = R$ 4,00 = 80 pontos
    assert (r.status_code, r.get_json()["error"]) == (422, "LIMITE_RESGATE_EXCEDIDO")
    assert r.get_json()["details"][0]["issue"] == "Máximo para este pedido: 80"
    ok = api.pedido([(SUCO, 1)], pontosResgatar=80)
    assert ok.status_code == 201 and (ok.get_json()["descontoPontosCentavos"], ok.get_json()["totalCentavos"]) == (400, 400)
    assert api.saldo()["saldo"] == 25                                   # a tentativa rejeitada não debitou nada


def test_resgate_com_valor_invalido_e_rejeitado(api):
    consentir(api)
    assert api.pedido([(CUSCUZ, 1)], pontosResgatar=-5).status_code == 422
    assert api.pedido([(CUSCUZ, 1)], pontosResgatar="dez").status_code == 422


def test_revogar_consentimento_bloqueia_novos_resgates_e_acumulos(api):
    ganhar_pontos(api, [(CARNE, 2)])                                    # 70 pontos
    api("DELETE", "/api/fidelidade/consentimento", "cliente")
    assert api.pedido([(CUSCUZ, 1)], pontosResgatar=5).status_code == 403
    api.pedido_pago([(CARNE, 1)])
    saldo = api.saldo()
    assert saldo["saldo"] == 70 and saldo["consentimentoAtivo"] is False   # sem acúmulo sem consentimento


def test_atendente_registra_pedido_com_resgate_do_cliente_consentido(api):
    ganhar_pontos(api, [(CARNE, 2)])
    r = api.pedido([(CARNE, 1)], perfil="atendente", canal="BALCAO", clienteId=1, pontosResgatar=20)
    assert r.status_code == 201 and r.get_json()["pontosResgatados"] == 20 and r.get_json()["clienteId"] == 1


# ------------------------------------ cancelamento e saldo ------------------------------
def test_cancelar_devolve_pontos_resgatados_e_retira_concedidos(api):
    ganhar_pontos(api, [(CARNE, 2)])                                    # +70
    pid = api.pedido_pago([(CARNE, 1)])                                 # +35 => 105
    assert api.saldo()["saldo"] == 105
    resgate = api.pedido([(CARNE, 1)], pontosResgatar=20).get_json()    # -20 => 85
    assert api.saldo()["saldo"] == 85
    api("POST", f"/api/pedidos/{resgate['id']}/cancelamento", "cliente")    # devolve 20 => 105
    assert api.saldo()["saldo"] == 105
    api("POST", f"/api/pedidos/{pid}/cancelamento", "cliente")              # retira os 35 concedidos => 70
    assert api.saldo()["saldo"] == 70


def test_cancelamento_pode_deixar_saldo_devedor_sem_ser_bloqueado(api):
    consentir(api)
    pid = api.pedido_pago([(CARNE, 1)])                                 # +35
    gasto = api.pedido([(CARNE, 1)], pontosResgatar=35).get_json()      # usa os 35 em outra compra
    assert gasto["pontosResgatados"] == 35 and api.saldo()["saldo"] == 0
    r = api("POST", f"/api/pedidos/{pid}/cancelamento", "cliente")      # precisa retirar 35 pontos já gastos
    assert r.status_code == 200 and r.get_json()["status"] == "CANCELADO"
    saldo = api.saldo()
    assert saldo["saldo"] == -35 and saldo["saldoDevedor"] is True and saldo["pontosDisponiveis"] == 0
    r = api.pedido([(CARNE, 1)], pontosResgatar=1)                      # nada disponível enquanto devedor
    assert (r.status_code, r.get_json()["error"]) == (409, "PONTOS_INSUFICIENTES")
    api.pedido_pago([(CARNE, 1)])                                       # +35 amortiza a dívida
    assert api.saldo()["saldo"] == 0


def test_regras_do_programa_aparecem_no_saldo(api):
    regras = api.saldo()["regras"]
    assert "1 ponto a cada R$ 1,00" in regras["acumulo"] and "R$ 0,05" in regras["resgate"]
