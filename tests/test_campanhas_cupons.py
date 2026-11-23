"""CRUD, escopo por perfil/unidade e regras de campanhas e cupons."""
from datetime import datetime, timedelta, timezone

from conftest import CARNE, CUSCUZ, SUCO, TAPIOCA


def iso(dias: int) -> str:
    """Instante UTC no formato da API, `dias` a partir de agora."""
    return (datetime.now(timezone.utc) + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")


def campanha(produto=SUCO, unidade=1, percentual=10, inicio=None, fim=None, dias=("QUARTA",), **extra):
    corpo = {"nome": "Campanha de teste", "produtoId": produto, "unidadeId": unidade,
             "percentualDesconto": percentual, "dataInicio": inicio or iso(1), "dataFim": fim or iso(30)}
    if dias is not None:
        corpo["diasSemana"] = list(dias)
    corpo.update(extra)
    return corpo


def erro(r):
    return r.status_code, r.get_json()["error"]


# ===================================== campanhas =====================================
def test_gerente_cria_campanha_da_propria_unidade_e_lista_apenas_o_seu_escopo(api):
    r = api("POST", "/api/campanhas", "gerente", campanha())
    corpo = r.get_json()
    assert r.status_code == 201 and corpo["diasSemana"] == ["QUARTA"] and corpo["ativa"] is True
    do_gerente = api("GET", "/api/campanhas", "gerente").get_json()
    assert [c["id"] for c in do_gerente["content"]] == [corpo["id"]]       # a campanha global do seed não aparece
    do_admin = api("GET", "/api/campanhas", "admin").get_json()
    assert do_admin["totalElements"] == 2                                   # seed (global) + criada
    assert api("GET", f"/api/campanhas/{corpo['id']}", "gerente").status_code == 200


def test_permissoes_de_campanha_por_perfil_e_escopo(api):
    assert erro(api("POST", "/api/campanhas", "gerente", campanha(unidade=None))) == (403, "ACESSO_NEGADO")
    assert erro(api("POST", "/api/campanhas", "gerente", campanha(unidade=2))) == (403, "ACESSO_NEGADO")
    for perfil in ("cliente", "cozinha", "atendente"):
        assert api("POST", "/api/campanhas", perfil, campanha()).status_code == 403
        assert api("GET", "/api/campanhas", perfil).status_code == 403
    assert api("POST", "/api/campanhas", None, campanha()).status_code == 401
    assert api("POST", "/api/campanhas", "admin", campanha(unidade=None)).status_code == 201   # global só ADMIN
    # gerente não enxerga nem altera a campanha global do seed (id 1)
    assert api("GET", "/api/campanhas/1", "gerente").status_code == 403
    assert api("PUT", "/api/campanhas/1", "gerente", campanha(produto=TAPIOCA)).status_code == 403
    assert api("DELETE", "/api/campanhas/1", "gerente").status_code == 403


def test_validacoes_de_campanha(api):
    casos = {
        "percentualDesconto": campanha(percentual=0),
        "dataFim": campanha(inicio=iso(10), fim=iso(5)),
        "diasSemana": campanha(dias=("FERIADO",)),
        "dataInicio": campanha(inicio="2030-01-01"),
        "nome": campanha(nome="x"),
    }
    for campo, corpo in casos.items():
        r = api("POST", "/api/campanhas", "gerente", corpo)
        assert r.status_code == 422, campo
        assert campo in {d["field"] for d in r.get_json()["details"]}, campo
    assert api("POST", "/api/campanhas", "gerente", campanha(percentual=101)).status_code == 422
    assert api("POST", "/api/campanhas", "gerente", campanha(produto=999)).status_code == 404
    assert api("POST", "/api/campanhas", "admin", campanha(unidade=999)).status_code == 404
    assert api("POST", "/api/campanhas", "gerente", None).status_code == 400
    assert api("GET", "/api/campanhas/999", "admin").status_code == 404


def test_periodos_sobrepostos_sao_rejeitados(api):
    """A campanha 'Terça da Tapioca' (global, só às terças) já existe no seed."""
    terca = api("POST", "/api/campanhas", "admin", campanha(produto=TAPIOCA, dias=("TERCA",)))
    assert erro(terca) == (409, "CAMPANHA_PERIODO_SOBREPOSTO")
    assert "Terça da Tapioca" in terca.get_json()["details"][0]["issue"]
    todos_os_dias = api("POST", "/api/campanhas", "admin", campanha(produto=TAPIOCA, dias=None))
    assert erro(todos_os_dias) == (409, "CAMPANHA_PERIODO_SOBREPOSTO")      # sem dias = todos, inclui terça
    assert api("POST", "/api/campanhas", "admin",
               campanha(produto=TAPIOCA, dias=("QUARTA",))).status_code == 201     # dia diferente: ok
    assert api("POST", "/api/campanhas", "admin",
               campanha(produto=TAPIOCA, dias=("TERCA",), inicio=iso(800), fim=iso(900))).status_code == 201  # período distinto
    assert api("POST", "/api/campanhas", "admin",
               campanha(produto=CUSCUZ, dias=("TERCA",))).status_code == 201        # produto distinto


def test_atualizar_campanha_ignora_a_si_mesma_mas_nao_aceita_conflito(api):
    a = api("POST", "/api/campanhas", "gerente", campanha(dias=("QUARTA",))).get_json()
    b = api("POST", "/api/campanhas", "gerente", campanha(dias=("QUINTA",))).get_json()
    ajuste = api("PUT", f"/api/campanhas/{a['id']}", "gerente", campanha(dias=("QUARTA",), percentual=25))
    assert ajuste.status_code == 200 and ajuste.get_json()["percentualDesconto"] == 25
    conflito = api("PUT", f"/api/campanhas/{b['id']}", "gerente", campanha(dias=("QUARTA",)))
    assert erro(conflito) == (409, "CAMPANHA_PERIODO_SOBREPOSTO")
    assert api("PUT", "/api/campanhas/999", "admin", campanha()).status_code == 404


def test_desativar_campanha_libera_o_periodo_e_remove_o_desconto(app, api):
    a = api("POST", "/api/campanhas", "gerente", campanha(dias=None)).get_json()
    assert erro(api("POST", "/api/campanhas", "gerente", campanha(dias=None))) == (409, "CAMPANHA_PERIODO_SOBREPOSTO")
    assert api("DELETE", f"/api/campanhas/{a['id']}", "gerente").status_code == 204
    assert api("GET", f"/api/campanhas/{a['id']}", "gerente").get_json()["ativa"] is False   # exclusão lógica
    assert api("POST", "/api/campanhas", "gerente", campanha(dias=None)).status_code == 201


def test_campanha_vigente_aplica_o_maior_desconto_e_so_no_dia_certo(app, api):
    from test_pedidos_pagamento import proximo_dia
    api("POST", "/api/campanhas", "gerente", campanha(produto=SUCO, percentual=30, dias=("QUARTA",), inicio=iso(-1)))
    app.extensions["relogio"] = lambda: proximo_dia(2)                  # próxima quarta-feira
    quarta = api.pedido([(SUCO, 1)]).get_json()
    assert (quarta["descontoCampanhasCentavos"], quarta["totalCentavos"]) == (240, 560)
    app.extensions["relogio"] = lambda: proximo_dia(3)                  # quinta-feira
    assert api.pedido([(SUCO, 1)]).get_json()["descontoCampanhasCentavos"] == 0


def test_campanha_local_nao_vale_em_outra_unidade(app, api):
    from test_pedidos_pagamento import proximo_dia
    api("POST", "/api/campanhas", "gerente", campanha(produto=SUCO, percentual=50, dias=("QUARTA",), inicio=iso(-1)))
    app.extensions["relogio"] = lambda: proximo_dia(2)
    assert api.pedido([(SUCO, 1)], unidade=1).get_json()["descontoCampanhasCentavos"] == 400
    assert api.pedido([(SUCO, 1)], unidade=2).get_json()["descontoCampanhasCentavos"] == 0


# ======================================= cupons ======================================
def cupom(codigo="VOLTA10", **extra):
    corpo = {"codigo": codigo, "tipo": "PERCENTUAL", "valor": 10, "unidadeId": 1}
    corpo.update(extra)
    return corpo


def test_gerente_cria_cupom_local_e_admin_cria_global(api):
    local = api("POST", "/api/cupons", "gerente", cupom("local-1"))
    assert local.status_code == 201 and local.get_json()["codigo"] == "LOCAL-1" and local.get_json()["usos"] == 0
    assert erro(api("POST", "/api/cupons", "gerente", cupom("global-x", unidadeId=None))) == (403, "ACESSO_NEGADO")
    assert api("POST", "/api/cupons", "gerente", cupom("outra-un", unidadeId=2)).status_code == 403
    assert api("POST", "/api/cupons", "admin", cupom("global-x", unidadeId=None)).status_code == 201
    for perfil in ("cliente", "cozinha", "atendente"):
        assert api("POST", "/api/cupons", perfil, cupom("nao-pode")).status_code == 403


def test_listagem_e_acesso_a_cupons_respeitam_o_escopo(api):
    local = api("POST", "/api/cupons", "gerente", cupom("so-centro")).get_json()
    api("POST", "/api/cupons", "admin", cupom("so-zona-sul", unidadeId=2))
    do_gerente = {c["codigo"] for c in api("GET", "/api/cupons", "gerente").get_json()["content"]}
    assert do_gerente == {"SO-CENTRO"}
    do_admin = {c["codigo"] for c in api("GET", "/api/cupons", "admin").get_json()["content"]}
    assert {"NORDESTE10", "PROMO5", "SO-CENTRO", "SO-ZONA-SUL"} == do_admin
    assert api("GET", f"/api/cupons/{local['id']}", "gerente").status_code == 200
    assert api("GET", "/api/cupons/1", "gerente").status_code == 403         # NORDESTE10 é global
    assert api("GET", "/api/cupons/999", "admin").status_code == 404


def test_validacoes_de_cupom(api):
    for campo, corpo in {"codigo": cupom("a!"), "tipo": cupom(tipo="BRINDE"), "valor": cupom(valor=0),
                         "validadeFim": cupom(validadeInicio="2031-01-01T00:00:00Z",
                                              validadeFim="2030-01-01T00:00:00Z"),
                         "limiteUso": cupom(limiteUso=0)}.items():
        r = api("POST", "/api/cupons", "admin", corpo)
        assert r.status_code == 422 and campo in {d["field"] for d in r.get_json()["details"]}, campo
    assert api("POST", "/api/cupons", "admin", cupom(valor=101)).status_code == 422     # percentual máximo 100
    assert api("POST", "/api/cupons", "admin", cupom("fixo", tipo="VALOR_FIXO", valor=5000)).status_code == 201
    assert api("POST", "/api/cupons", "admin", cupom(unidadeId=999)).status_code == 404


def test_codigo_de_cupom_e_unico_sem_diferenciar_maiusculas(api):
    assert api("POST", "/api/cupons", "admin", cupom("PROMO5", unidadeId=None)).status_code == 409
    assert erro(api("POST", "/api/cupons", "admin", cupom("nordeste10", unidadeId=None))) == (409, "CUPOM_CODIGO_DUPLICADO")
    novo = api("POST", "/api/cupons", "gerente", cupom("renomear")).get_json()
    assert api("PUT", f"/api/cupons/{novo['id']}", "gerente", cupom("PROMO5")).status_code == 409
    ok = api("PUT", f"/api/cupons/{novo['id']}", "gerente", cupom("renomear", valor=20))     # mantém o próprio código
    assert ok.status_code == 200 and ok.get_json()["valor"] == 20
    assert api("PUT", "/api/cupons/999", "admin", cupom()).status_code == 404


def test_cupom_fora_da_vigencia_e_rejeitado_no_pedido(api):
    api("POST", "/api/cupons", "admin", cupom("EXPIRADO", unidadeId=None, validadeInicio="2020-01-01T00:00:00Z",
                                              validadeFim="2020-12-31T23:59:59Z"))
    api("POST", "/api/cupons", "admin", cupom("FUTURO", unidadeId=None, validadeInicio="2099-01-01T00:00:00Z"))
    for codigo in ("EXPIRADO", "FUTURO"):
        r = api.pedido([(CUSCUZ, 1)], cupomCodigo=codigo)
        assert erro(r) == (422, "CUPOM_FORA_DA_VIGENCIA"), codigo


def test_reativar_cupom_via_put(api):
    api("DELETE", "/api/cupons/2", "admin")                                    # PROMO5
    assert api.pedido([(CARNE, 1)], cupomCodigo="PROMO5").get_json()["error"] == "CUPOM_INVALIDO"
    atual = api("GET", "/api/cupons/2", "admin").get_json()
    assert atual["ativo"] is False
    corpo = {"codigo": "PROMO5", "tipo": "VALOR_FIXO", "valor": 500, "valorMinimoCentavos": 3000, "ativo": True}
    assert api("PUT", "/api/cupons/2", "admin", corpo).status_code == 200
    assert api.pedido([(CARNE, 1)], cupomCodigo="PROMO5").status_code == 201


def test_cupom_aplicado_apos_campanha_e_antes_dos_pontos(app, api):
    from test_pedidos_pagamento import proximo_dia
    app.extensions["relogio"] = lambda: proximo_dia(1)                         # terça: tapioca -20%
    p = api.pedido([(TAPIOCA, 5)], cupomCodigo="NORDESTE10").get_json()      # 6000 -1200 = 4800; -10% = 480
    assert (p["subtotalCentavos"], p["descontoCampanhasCentavos"], p["descontoCupomCentavos"],
            p["totalCentavos"]) == (6000, 1200, 480, 4320)
