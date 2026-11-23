from datetime import datetime, timedelta, timezone

from conftest import CARNE, CUSCUZ, SUCO, TAPIOCA, configuracao

from raizesdonordeste import create_app


def proximo_dia(dia_semana: int, hora_utc: int = 15) -> datetime:
    """Próxima data (futura) com o dia da semana pedido (0=segunda), em UTC."""
    base = datetime.now(timezone.utc) + timedelta(days=1)
    while base.weekday() != dia_semana:
        base += timedelta(days=1)
    return base.replace(hour=hora_utc, minute=0, second=0, microsecond=0)


# --------------------------------------- criação ---------------------------------------
def test_criar_pedido_calcula_valores_e_reserva_estoque(api):
    r = api.pedido([(CUSCUZ, 2), (SUCO, 1)], canal="TOTEM")
    assert r.status_code == 201
    p = r.get_json()
    assert (p["subtotalCentavos"], p["totalCentavos"]) == (2800, 2800)
    assert (p["status"], p["statusPagamento"], p["canalPedido"]) == ("AGUARDANDO_PAGAMENTO", "PENDENTE", "TOTEM")
    assert [i["quantidade"] for i in p["itens"]] == [2, 1] and p["historico"][0]["para"] == "AGUARDANDO_PAGAMENTO"
    assert api.estoque(CUSCUZ) == 48 and api.estoque(SUCO) == 49
    mov = api("GET", f"/api/estoque/{CUSCUZ}/movimentacoes", "gerente").get_json()["content"][0]
    assert (mov["motivo"], mov["pedidoId"]) == ("RESERVA_PEDIDO", p["id"])


def test_validacao_do_corpo_do_pedido(api):
    r = api("POST", "/api/pedidos", "cliente", {"unidadeId": 1, "canalPedido": "FAX", "itens": [{"produtoId": 1, "quantidade": 0}]})
    campos = {d["field"] for d in r.get_json()["details"]}
    assert r.status_code == 422 and {"canalPedido", "itens[0].quantidade"} <= campos
    assert api("POST", "/api/pedidos", "cliente", {"unidadeId": 1, "canalPedido": "APP", "itens": []}).status_code == 422
    assert api("POST", "/api/pedidos", "cozinha", {}).status_code == 403
    assert api("POST", "/api/pedidos", json={}).status_code == 401


def test_estoque_insuficiente_e_atomico(api):
    api("PUT", f"/api/estoque/{CUSCUZ}", "gerente", {"quantidade": 5})
    r = api.pedido([(SUCO, 1), (CUSCUZ, 10)])
    corpo = r.get_json()
    assert (r.status_code, corpo["error"]) == (409, "ESTOQUE_INSUFICIENTE")
    assert corpo["details"] == [{"field": "itens[1].quantidade", "issue": "Disponível: 5"}]
    assert api.estoque(SUCO) == 50                                  # nada foi reservado
    assert corpo["requestId"] and corpo["path"] == "/api/pedidos"


def test_itens_repetidos_sao_somados(api):
    p = api.pedido([(CUSCUZ, 2), (CUSCUZ, 3)]).get_json()
    assert len(p["itens"]) == 1 and p["itens"][0]["quantidade"] == 5


def test_atendente_registra_pedido_para_cliente(api):
    assert api.pedido([(CUSCUZ, 1)], perfil="atendente").status_code == 422          # falta clienteId
    ok = api.pedido([(CUSCUZ, 1)], perfil="atendente", canal="BALCAO", clienteId=1)
    assert ok.status_code == 201 and ok.get_json()["clienteId"] == 1
    assert api.pedido([(CUSCUZ, 1)], perfil="atendente", unidade=2, clienteId=1).status_code == 403
    assert api.pedido([(CUSCUZ, 1)], perfil="cliente", clienteId=99).status_code == 403


# ------------------------------------- idempotência ------------------------------------
def test_idempotency_key(api):
    cab = {"Idempotency-Key": "chave-12345678"}
    corpo = {"unidadeId": 1, "canalPedido": "APP", "itens": [{"produtoId": CUSCUZ, "quantidade": 2}]}
    primeiro = api("POST", "/api/pedidos", "cliente", corpo, cab)
    repetido = api("POST", "/api/pedidos", "cliente", corpo, cab)
    assert (primeiro.status_code, repetido.status_code) == (201, 200)
    assert repetido.get_json()["id"] == primeiro.get_json()["id"]
    assert repetido.headers["Idempotency-Replayed"] == "true"
    assert api.estoque(CUSCUZ) == 48                                # reservou uma única vez
    diferente = api("POST", "/api/pedidos", "cliente", {**corpo, "itens": [{"produtoId": CUSCUZ, "quantidade": 3}]}, cab)
    assert (diferente.status_code, diferente.get_json()["error"]) == (409, "CHAVE_IDEMPOTENCIA_REUTILIZADA")
    assert api("POST", "/api/pedidos", "cliente", corpo, {"Idempotency-Key": "curta"}).status_code == 422
    outro = api("POST", "/api/pedidos", "atendente", {**corpo, "clienteId": 1}, cab)   # chave é escopada ao usuário
    assert outro.status_code == 201


# ----------------------------------- campanhas e cupons --------------------------------
def test_campanha_terca_da_tapioca_aplica_desconto(app, api):
    app.extensions["relogio"] = lambda: proximo_dia(1)
    p = api.pedido([(TAPIOCA, 2)]).get_json()
    assert (p["subtotalCentavos"], p["descontoCampanhasCentavos"], p["totalCentavos"]) == (2400, 480, 1920)
    assert p["itens"][0]["campanhaId"] == 1
    app.extensions["relogio"] = lambda: proximo_dia(2)             # quarta-feira
    q = api.pedido([(TAPIOCA, 2)]).get_json()
    assert (q["descontoCampanhasCentavos"], q["totalCentavos"]) == (0, 2400)


def test_cupons_percentual_valor_fixo_e_regras(api, app):
    app.extensions["relogio"] = lambda: proximo_dia(2)             # evita a campanha de terça
    p = api.pedido([(CARNE, 1)], cupomCodigo="nordeste10").get_json()   # 3500 - 10%
    assert (p["descontoCupomCentavos"], p["totalCentavos"], p["cupomCodigo"]) == (350, 3150, "NORDESTE10")
    r = api.pedido([(CUSCUZ, 1)], cupomCodigo="PROMO5")                  # mínimo R$ 30
    assert (r.status_code, r.get_json()["error"]) == (422, "CUPOM_VALOR_MINIMO")
    ok = api.pedido([(CARNE, 1)], cupomCodigo="PROMO5").get_json()
    assert ok["totalCentavos"] == 3000
    assert api.pedido([(CUSCUZ, 1)], cupomCodigo="NAOEXISTE").get_json()["error"] == "CUPOM_INVALIDO"


def test_cupom_local_limite_de_uso_e_liberacao_no_cancelamento(api):
    criado = api("POST", "/api/cupons", "gerente", {"codigo": "so-centro", "tipo": "VALOR_FIXO", "valor": 100,
                                                    "unidadeId": 1, "limiteUso": 1})
    assert criado.status_code == 201 and criado.get_json()["codigo"] == "SO-CENTRO"
    primeiro = api.pedido([(CUSCUZ, 1)], cupomCodigo="SO-CENTRO").get_json()
    esgotado = api.pedido([(CUSCUZ, 1)], cupomCodigo="SO-CENTRO")
    assert (esgotado.status_code, esgotado.get_json()["error"]) == (409, "CUPOM_ESGOTADO")
    assert api.pedido([(CUSCUZ, 1)], unidade=2, cupomCodigo="SO-CENTRO").get_json()["error"] == "CUPOM_OUTRA_UNIDADE"
    api("POST", f"/api/pedidos/{primeiro['id']}/cancelamento", "cliente")
    assert api.pedido([(CUSCUZ, 1)], cupomCodigo="SO-CENTRO").status_code == 201      # uso liberado


def test_cupom_desativado_deixa_de_valer(api):
    api("DELETE", "/api/cupons/1", "admin")
    assert api.pedido([(CUSCUZ, 1)], cupomCodigo="NORDESTE10").get_json()["error"] == "CUPOM_INVALIDO"


def test_pedido_totalmente_coberto_e_isento_de_pagamento(api):
    api("POST", "/api/cupons", "admin", {"codigo": "GRATIS", "tipo": "PERCENTUAL", "valor": 100})
    p = api.pedido([(CUSCUZ, 1)], cupomCodigo="GRATIS").get_json()
    assert (p["totalCentavos"], p["status"], p["statusPagamento"]) == (0, "RECEBIDO", "ISENTO")
    assert api.pagar(p["id"]).status_code == 409


# ------------------------------------ escopo e consulta --------------------------------
def test_escopo_de_consulta_por_perfil(api):
    pid = api.pedido([(CUSCUZ, 1)]).get_json()["id"]
    api.pedido([(CUSCUZ, 1)], perfil="atendente", clienteId=1)
    outro = api("POST", "/api/auth/login", json={"email": "gerente@raizes.com", "senha": "gerente123"})
    assert outro.status_code == 200
    # cliente 2 (novo) não enxerga o pedido do cliente 1
    from test_autenticacao_usuarios import corpo_registro
    api("POST", "/api/usuarios", json=corpo_registro(api))
    token = api("POST", "/api/auth/login", json={"email": "maria@exemplo.com", "senha": "senha-forte-1"}).get_json()["token"]
    assert api("GET", f"/api/pedidos/{pid}", token=token).status_code == 404
    assert api("GET", "/api/pedidos", token=token).get_json()["totalElements"] == 0
    assert api("GET", "/api/pedidos", "cozinha").get_json()["totalElements"] == 2
    assert api("GET", f"/api/pedidos/{pid}", "cozinha").status_code == 200
    assert api("GET", "/api/pedidos?unidadeId=2", "cozinha").status_code == 403
    assert api("GET", "/api/pedidos?unidadeId=2", "admin").get_json()["totalElements"] == 0


def test_filtros_combinaveis_e_validados(api):
    api.pedido([(CUSCUZ, 1)], canal="APP")
    api.pedido([(CUSCUZ, 1)], canal="TOTEM")
    r = api("GET", "/api/pedidos?canalPedido=TOTEM&status=AGUARDANDO_PAGAMENTO&unidadeId=1&page=0&limit=10", "admin")
    assert r.get_json()["totalElements"] == 1 and r.get_json()["content"][0]["canalPedido"] == "TOTEM"
    assert api("GET", "/api/pedidos?status=INEXISTENTE", "admin").status_code == 422
    assert api("GET", "/api/pedidos?canalPedido=xx&unidadeId=abc", "admin").status_code == 422


# --------------------------------------- status ----------------------------------------
def test_fluxo_operacional_completo(api):
    pid = api.pedido([(CUSCUZ, 1)]).get_json()["id"]
    r = api.status(pid, "EM_PREPARO", "cozinha")                                  # ainda sem pagamento
    assert (r.status_code, r.get_json()["error"]) == (409, "TRANSICAO_DE_STATUS_INVALIDA")
    assert api.pagar(pid).status_code == 201
    assert api.status(pid, "PRONTO", "cozinha").status_code == 409                # não pode pular etapa
    assert api.status(pid, "EM_PREPARO", "cozinha").get_json()["status"] == "EM_PREPARO"
    assert api.status(pid, "PRONTO", "cozinha").get_json()["status"] == "PRONTO"
    assert api.status(pid, "ENTREGUE", "cozinha").status_code == 403              # entrega é do atendente
    assert api.status(pid, "ENTREGUE", "cliente").status_code == 403
    final = api.status(pid, "ENTREGUE", "atendente").get_json()
    assert final["status"] == "ENTREGUE"
    assert [h["para"] for h in final["historico"]] == ["AGUARDANDO_PAGAMENTO", "RECEBIDO", "EM_PREPARO", "PRONTO", "ENTREGUE"]
    assert api.status(pid, "EM_PREPARO", "gerente").status_code == 409           # estado final


def test_status_cancelado_exige_endpoint_proprio(api):
    pid = api.pedido_pago([(CUSCUZ, 1)])
    r = api.status(pid, "CANCELADO", "gerente")
    assert (r.status_code, r.get_json()["error"]) == (422, "STATUS_INVALIDO")
    assert api.status(pid, "XPTO", "gerente").status_code == 422


# ------------------------------------- cancelamento ------------------------------------
def test_cancelar_pedido_nao_pago_devolve_estoque(api):
    pid = api.pedido([(CUSCUZ, 4)]).get_json()["id"]
    assert api.estoque(CUSCUZ) == 46
    r = api("POST", f"/api/pedidos/{pid}/cancelamento", "cliente", {"motivo": "Desisti"})
    corpo = r.get_json()
    assert (r.status_code, corpo["status"], corpo["statusPagamento"]) == (200, "CANCELADO", "CANCELADO")
    assert api.estoque(CUSCUZ) == 50
    assert api("POST", f"/api/pedidos/{pid}/cancelamento", "cliente").status_code == 409     # já cancelado


def test_cancelar_pedido_pago_estorna_e_devolve_estoque(api):
    pid = api.pedido_pago([(CUSCUZ, 2)])
    corpo = api("POST", f"/api/pedidos/{pid}/cancelamento", "cliente").get_json()
    assert (corpo["status"], corpo["statusPagamento"]) == ("CANCELADO", "ESTORNADO")
    assert api.estoque(CUSCUZ) == 50
    tentativas = api("GET", f"/api/pedidos/{pid}/pagamento/tentativas", "cliente").get_json()
    assert [(t["tipo"], t["status"]) for t in tentativas] == [("PAGAMENTO", "APROVADO"), ("ESTORNO", "CONFIRMADO")]


def test_cancelar_em_preparo_nao_devolve_estoque(api):
    pid = api.pedido_pago([(CUSCUZ, 2)])
    api.status(pid, "EM_PREPARO", "cozinha")
    assert api("POST", f"/api/pedidos/{pid}/cancelamento", "cliente").status_code == 409   # cliente não cancela mais
    corpo = api("POST", f"/api/pedidos/{pid}/cancelamento", "atendente", {"motivo": "Cliente desistiu"}).get_json()
    assert (corpo["status"], corpo["statusPagamento"]) == ("CANCELADO", "ESTORNADO")
    assert api.estoque(CUSCUZ) == 48                        # itens já consumidos: não retornam ao saldo


def test_entregue_nao_pode_ser_cancelado(api):
    pid = api.pedido_pago([(CUSCUZ, 1)])
    for perfil, novo in (("cozinha", "EM_PREPARO"), ("cozinha", "PRONTO"), ("atendente", "ENTREGUE")):
        assert api.status(pid, novo, perfil).status_code == 200
    r = api("POST", f"/api/pedidos/{pid}/cancelamento", "admin")
    assert (r.status_code, r.get_json()["error"]) == (409, "PEDIDO_NAO_CANCELAVEL")


def test_estorno_com_gateway_indisponivel_preserva_estado(app, api):
    pid = api.pedido_pago([(CUSCUZ, 2)])
    app.extensions["gateway"].forcar_estorno = "INDISPONIVEL"
    r = api("POST", f"/api/pedidos/{pid}/cancelamento", "cliente")
    assert (r.status_code, r.get_json()["error"]) == (503, "GATEWAY_PAGAMENTO_INDISPONIVEL")
    atual = api("GET", f"/api/pedidos/{pid}", "cliente").get_json()
    assert (atual["status"], atual["statusPagamento"]) == ("RECEBIDO", "APROVADO")
    assert api.estoque(CUSCUZ) == 48
    app.extensions["gateway"].forcar_estorno = "CONFIRMADO"
    assert api("POST", f"/api/pedidos/{pid}/cancelamento", "cliente").get_json()["statusPagamento"] == "ESTORNADO"
    estornos = [t for t in api("GET", f"/api/pedidos/{pid}/pagamento/tentativas", "cliente").get_json() if t["tipo"] == "ESTORNO"]
    assert len(estornos) == 1                                   # nenhuma solicitação duplicada


# ---------------------------------------- pagamento ------------------------------------
def test_pagamento_aprovado_retorna_payload_do_gateway(api):
    pid = api.pedido([(CUSCUZ, 2)]).get_json()["id"]
    r = api.pagar(pid, forma="CARTAO_CREDITO")
    corpo = r.get_json()
    assert r.status_code == 201 and corpo["status"] == "APROVADO" and corpo["numeroTentativa"] == 1
    assert corpo["pedidoStatus"] == "RECEBIDO" and corpo["pedidoStatusPagamento"] == "APROVADO"
    assert corpo["gateway"]["requisicao"]["valor"] == {"centavos": 2000, "moeda": "BRL"}
    assert corpo["gateway"]["requisicao"]["formaPagamento"] == "CARTAO_CREDITO"
    assert corpo["gateway"]["resposta"]["status"] == "APROVADO" and corpo["referenciaGateway"].startswith("gw_")


def test_pagamento_recusado_permite_nova_tentativa(api):
    pid = api.pedido([(CUSCUZ, 1)]).get_json()["id"]
    recusado = api.pagar(pid, forma="CARTAO_DEBITO", forcar="RECUSADO")
    assert recusado.status_code == 201 and recusado.get_json()["status"] == "RECUSADO"
    assert recusado.get_json()["pedidoStatus"] == "AGUARDANDO_PAGAMENTO"
    aprovado = api.pagar(pid, forma="PIX", forcar="APROVADO")
    assert aprovado.get_json()["status"] == "APROVADO" and aprovado.get_json()["numeroTentativa"] == 2
    tentativas = api("GET", f"/api/pedidos/{pid}/pagamento/tentativas", "cliente").get_json()
    assert [t["status"] for t in tentativas] == ["RECUSADO", "APROVADO"]
    assert api.pagar(pid).status_code == 409                     # já pago


def test_gateway_indisponivel_nao_consome_tentativa(api):
    pid = api.pedido([(CUSCUZ, 1)]).get_json()["id"]
    r = api.pagar(pid, forcar="INDISPONIVEL")
    assert (r.status_code, r.get_json()["error"]) == (503, "GATEWAY_PAGAMENTO_INDISPONIVEL")
    assert api("GET", f"/api/pedidos/{pid}/pagamento/tentativas", "cliente").get_json() == []
    assert api("GET", f"/api/pedidos/{pid}", "cliente").get_json()["status"] == "AGUARDANDO_PAGAMENTO"
    assert api.pagar(pid).get_json()["numeroTentativa"] == 1     # repetição segura


def test_validacoes_e_escopo_do_pagamento(api):
    pid = api.pedido([(CUSCUZ, 1)]).get_json()["id"]
    assert api("POST", f"/api/pedidos/{pid}/pagamento", "cliente", {"formaPagamento": "BOLETO"}).status_code == 422
    assert api.pagar(pid, forcar="TALVEZ").status_code == 422
    assert api.pagar(pid, perfil="cozinha").status_code == 403
    assert api.pagar(999).status_code == 404
    assert api.pagar(pid, perfil="atendente").status_code == 201          # atendente da unidade paga no balcão


def test_perfil_prod_ignora_header_de_simulacao_e_desliga_swagger(tmp_path):
    cfg = configuracao(profile="prod", jwt_secret="x" * 40, db_path=str(tmp_path / "prod.db"),
                       seed_enabled=True, pagamento_forcar_status="", cors_allowed_origins=())
    app = create_app(cfg)
    app.extensions["gateway"].sorteio = lambda: 0.0                  # sorteio favorável: aprova
    c = app.test_client()
    token = c.post("/api/auth/login", json={"email": "cliente@raizes.com", "senha": "cliente123"}).get_json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    pid = c.post("/api/pedidos", headers=h, json={"unidadeId": 1, "canalPedido": "WEB",
                                                    "itens": [{"produtoId": CUSCUZ, "quantidade": 1}]}).get_json()["id"]
    r = c.post(f"/api/pedidos/{pid}/pagamento", headers={**h, "X-Forcar-Status-Pagamento": "RECUSADO"},
               json={"formaPagamento": "PIX"})
    assert r.get_json()["status"] == "APROVADO"                      # header ignorado em produção
    assert c.get("/api/v3/api-docs").status_code == 404
    assert c.get("/api/swagger-ui.html").status_code == 404
