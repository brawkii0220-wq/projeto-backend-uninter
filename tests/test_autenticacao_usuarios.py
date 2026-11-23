import dataclasses
import logging

from raizesdonordeste.service.documento_legal_service import DocumentoLegal


def termos(api):
    return api("GET", "/api/documentos-legais/termos-uso").get_json()


def corpo_registro(api, **extra):
    t = termos(api)
    corpo = {"nome": "Maria Silva", "email": "maria@exemplo.com", "senha": "senha-forte-1",
             "aceiteTermosUso": True, "versaoTermosUso": t["versao"], "hashTermosUso": t["hashSha256"]}
    corpo.update(extra)
    return corpo


def test_login_ok_e_falhas(api):
    ok = api("POST", "/api/auth/login", json={"email": "cliente@raizes.com", "senha": "cliente123"})
    assert ok.status_code == 200 and ok.get_json()["tipo"] == "Bearer"
    ruim = api("POST", "/api/auth/login", json={"email": "cliente@raizes.com", "senha": "errada"})
    assert (ruim.status_code, ruim.get_json()["error"]) == (401, "CREDENCIAIS_INVALIDAS")
    assert api("POST", "/api/auth/login", json={"email": "naoexiste@x.com", "senha": "qualquer123"}).status_code == 401
    assert api("POST", "/api/auth/login", json={"email": "x"}).status_code == 422
    assert api("POST", "/api/auth/login").status_code == 400


def test_endpoints_protegidos_exigem_token_valido(api):
    assert api("GET", "/api/unidades").status_code == 401
    r = api("GET", "/api/unidades", token="abc.def.ghi")
    assert (r.status_code, r.get_json()["error"]) == (401, "TOKEN_INVALIDO")


def test_rbac_por_perfil(api):
    assert api("POST", "/api/unidades", "cliente", {"nome": "Nova", "cidade": "Olinda"}).status_code == 403
    assert api("POST", "/api/unidades", "gerente", {"nome": "Nova", "cidade": "Olinda"}).status_code == 403
    assert api("POST", "/api/unidades", "admin", {"nome": "Nova", "cidade": "Olinda"}).status_code == 201
    assert api("GET", "/api/usuarios", "cliente").status_code == 403
    assert api("GET", "/api/usuarios", "admin").get_json()["totalElements"] == 5


def test_registro_publico_cria_apenas_cliente(api):
    r = api("POST", "/api/usuarios", json=corpo_registro(api, perfil="ADMIN", cpf="529.982.247-25"))
    assert r.status_code == 201
    dto = r.get_json()
    assert dto["perfil"] == "CLIENTE" and dto["cpf"] == "52998224725" and "senha" not in dto
    login = api("POST", "/api/auth/login", json={"email": "maria@exemplo.com", "senha": "senha-forte-1"})
    assert login.status_code == 200


def test_registro_valida_termos_e_dados(api):
    assert api("POST", "/api/usuarios", json=corpo_registro(api, aceiteTermosUso=False)).status_code == 422
    r = api("POST", "/api/usuarios", json=corpo_registro(api, hashTermosUso="0" * 64))
    assert (r.status_code, r.get_json()["error"]) == (409, "TERMOS_USO_VERSAO_DESATUALIZADA")
    r = api("POST", "/api/usuarios", json=corpo_registro(api, email="cliente@raizes.com"))
    assert (r.status_code, r.get_json()["error"]) == (409, "EMAIL_JA_CADASTRADO")
    r = api("POST", "/api/usuarios", json=corpo_registro(api, cpf="111.111.111-11", senha="curta"))
    campos = {d["field"] for d in r.get_json()["details"]}
    assert r.status_code == 422 and {"cpf", "senha"} <= campos


def test_nova_versao_dos_termos_bloqueia_ate_novo_aceite(app, api):
    atual = app.extensions["documentos"]["TERMOS_USO"]
    app.extensions["documentos"]["TERMOS_USO"] = dataclasses.replace(atual, versao="2.0", hash_sha256="f" * 64)
    r = api("GET", "/api/pedidos", "cliente")
    assert (r.status_code, r.get_json()["error"]) == (409, "TERMOS_USO_NAO_ACEITOS")
    assert api("GET", "/api/documentos-legais/termos-uso/aceite", "cliente").get_json()["aceiteVigente"] is False
    r = api("PUT", "/api/documentos-legais/termos-uso/aceite", "cliente", {"versao": "1.0"})
    assert r.status_code == 409                       # versão informada diferente da vigente
    novo = api("PUT", "/api/documentos-legais/termos-uso/aceite", "cliente", {"versao": "2.0", "hashSha256": "f" * 64})
    assert novo.status_code == 201 and novo.get_json()["ultimoAceite"]["versao"] == "2.0"
    assert api("PUT", "/api/documentos-legais/termos-uso/aceite", "cliente").status_code == 200   # idempotente
    assert api("GET", "/api/pedidos", "cliente").status_code == 200


def test_atualizar_usuario_e_restricoes_de_perfil(api):
    cliente_id = 1
    r = api("PUT", f"/api/usuarios/{cliente_id}", "cliente", {"nome": "Cliente Renomeado"})
    assert r.status_code == 200 and r.get_json()["nome"] == "Cliente Renomeado"
    assert api("PUT", f"/api/usuarios/{cliente_id}", "cliente", {"perfil": "ADMIN"}).status_code == 403
    assert api("PUT", "/api/usuarios/2", "cliente", {"nome": "Outro"}).status_code == 403
    sem_unidade = api("PUT", f"/api/usuarios/{cliente_id}", "admin", {"perfil": "GERENTE"})
    assert sem_unidade.status_code == 422
    ok = api("PUT", f"/api/usuarios/{cliente_id}", "admin", {"perfil": "GERENTE", "unidadeId": 2})
    assert ok.get_json()["perfil"] == "GERENTE" and ok.get_json()["unidadeId"] == 2


def test_nao_remove_ultimo_admin(api):
    r = api("PUT", "/api/usuarios/5", "admin", {"perfil": "CLIENTE"})
    assert (r.status_code, r.get_json()["error"]) == (409, "ULTIMO_ADMIN")
    assert api("DELETE", "/api/usuarios/5", "admin").status_code == 409


def test_anonimizacao_lgpd_preserva_pedidos(api):
    pid = api.pedido_pago([(2, 1)])
    assert api("DELETE", "/api/usuarios/1", "cliente").status_code == 204
    r = api("POST", "/api/auth/login", json={"email": "cliente@raizes.com", "senha": "cliente123"})
    assert r.status_code == 401
    assert api("GET", "/api/pedidos/1", "cliente").status_code == 401        # token antigo deixa de valer
    usuario = api("GET", "/api/usuarios/1", "admin").get_json()
    assert usuario["nome"] == "Usuário anonimizado" and usuario["cpf"] is None
    assert usuario["email"].endswith("@anonimizado.invalid")
    assert api("GET", f"/api/pedidos/{pid}", "admin").status_code == 200       # pedido preservado


def test_logs_nao_expõem_email(api):
    registros = []

    class Coletor(logging.Handler):
        def emit(self, record):
            registros.append(record.getMessage())

    logger = logging.getLogger("raizes.auth")
    coletor = Coletor()
    logger.addHandler(coletor)
    try:
        api("POST", "/api/auth/login", json={"email": "cliente@raizes.com", "senha": "errada-123"})
    finally:
        logger.removeHandler(coletor)
    assert registros and all("cliente@raizes.com" not in m for m in registros)
    assert any("u_" in m for m in registros)
