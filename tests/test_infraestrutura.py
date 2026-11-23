"""Infraestrutura: correlação, contrato de erro, CORS, perfis, JWT, senhas, migrations, seed e documentação."""
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from conftest import configuracao
from raizesdonordeste import Settings, create_app
from raizesdonordeste.config.settings import SEGREDO_DEV
from raizesdonordeste.repository import database
from raizesdonordeste.security import senhas
from raizesdonordeste.util.pseudonimizacao import pseudonimizar

CHAVES_ERRO = {"error", "message", "details", "timestamp", "path", "requestId"}


def app_prod(tmp_path, **extra):
    base = dict(profile="prod", jwt_secret="p" * 40, db_path=str(tmp_path / "prod.db"), seed_enabled=False,
                pagamento_forcar_status="", cors_allowed_origins=("https://app.exemplo.com.br",),
                cors_allowed_headers=("Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"))
    base.update(extra)
    return create_app(configuracao(**base))


# ================================= X-Request-ID ======================================
def test_request_id_valido_e_propagado_na_resposta_e_no_erro(client):
    r = client.get("/api/pedidos", headers={"X-Request-ID": "req-abc-12345"})
    assert r.headers["X-Request-ID"] == "req-abc-12345"
    assert r.get_json()["requestId"] == "req-abc-12345"


@pytest.mark.parametrize("enviado", [None, "curto", "tem espaço e <script>", "x" * 101, ""])
def test_request_id_ausente_ou_invalido_e_substituido_por_uuid(client, enviado):
    cabecalhos = {} if enviado is None else {"X-Request-ID": enviado}
    r = client.get("/api/produtos", headers=cabecalhos)
    assert str(uuid.UUID(r.headers["X-Request-ID"])) == r.headers["X-Request-ID"]


def test_cada_requisicao_recebe_um_identificador_proprio(client):
    ids = {client.get("/api/produtos").headers["X-Request-ID"] for _ in range(5)}
    assert len(ids) == 5


# ================================= contrato de erro ==================================
def test_todas_as_falhas_seguem_o_mesmo_contrato(client, api):
    def json_invalido():
        return client.post("/api/auth/login", data="{oops", content_type="application/json")

    casos = [
        (client.get("/xyz"), 404, "RECURSO_NAO_ENCONTRADO"),
        (client.get("/api/rota-inexistente"), 404, "RECURSO_NAO_ENCONTRADO"),
        (client.delete("/api/auth/login"), 405, "METODO_NAO_PERMITIDO"),
        (client.get("/api/pedidos"), 401, "NAO_AUTENTICADO"),
        (api("GET", "/api/pedidos", token="lixo.lixo.lixo"), 401, "TOKEN_INVALIDO"),
        (api("GET", "/api/usuarios", "cliente"), 403, "ACESSO_NEGADO"),
        (api("GET", "/api/usuarios/999", "admin"), 404, "RECURSO_NAO_ENCONTRADO"),
        (json_invalido(), 400, "CORPO_INVALIDO"),
        (api("POST", "/api/unidades", "admin", {}), 422, "VALIDACAO_ERRO"),
        (api("POST", "/api/auth/login", json={"email": "cliente@raizes.com", "senha": "errada-1"}), 401,
         "CREDENCIAIS_INVALIDAS"),
    ]
    for resposta, status, codigo in casos:
        corpo = resposta.get_json()
        assert (resposta.status_code, corpo["error"]) == (status, codigo)
        assert set(corpo) == CHAVES_ERRO and isinstance(corpo["details"], list)
        assert corpo["requestId"] == resposta.headers["X-Request-ID"]
        assert corpo["timestamp"].endswith("Z") and corpo["path"].startswith("/")


def test_mensagens_de_erro_http_sao_em_portugues(client):
    assert client.get("/api/rota-inexistente").get_json()["message"] == "Recurso não encontrado."
    assert "não permitido" in client.delete("/api/auth/login").get_json()["message"]


def test_erros_de_validacao_listam_cada_campo(api):
    r = api("POST", "/api/produtos", "admin", {"nome": "x", "precoCentavos": -1})
    detalhes = {d["field"]: d["issue"] for d in r.get_json()["details"]}
    assert r.status_code == 422 and {"nome", "precoCentavos"} <= set(detalhes)


def test_erro_inesperado_responde_500_sem_vazar_detalhes_internos():
    app = create_app(configuracao())

    @app.get("/api/explode")
    def _explode():
        raise ValueError("segredo-interno-do-servidor")

    r = app.test_client().get("/api/explode")
    corpo = r.get_json()
    assert (r.status_code, corpo["error"]) == (500, "ERRO_INTERNO")
    assert "segredo-interno" not in r.get_data(as_text=True) and set(corpo) == CHAVES_ERRO


# =================================== paginação =======================================
def test_paginacao_padrao_e_totais(api):
    corpo = api("GET", "/api/unidades?limit=1", "cliente").get_json()
    assert set(corpo) == {"content", "page", "limit", "totalElements", "totalPages"}
    assert (len(corpo["content"]), corpo["totalElements"], corpo["totalPages"]) == (1, 2, 2)
    segunda = api("GET", "/api/unidades?limit=1&page=1", "cliente").get_json()
    assert segunda["content"][0]["id"] != corpo["content"][0]["id"]
    assert api("GET", "/api/unidades?page=9", "cliente").get_json()["content"] == []
    assert api("GET", "/api/unidades", "cliente").get_json()["limit"] == 10


@pytest.mark.parametrize("consulta", ["limit=101", "limit=0", "page=-1", "page=abc", "limit=1.5"])
def test_paginacao_invalida_e_rejeitada(api, consulta):
    r = api("GET", f"/api/unidades?{consulta}", "cliente")
    assert (r.status_code, r.get_json()["error"]) == (422, "VALIDACAO_ERRO")


# ====================================== CORS =========================================
def test_cors_origem_permitida_recebe_cabecalhos(client):
    r = client.get("/api/produtos", headers={"Origin": "http://localhost:3000"})
    assert r.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert r.headers["Access-Control-Allow-Credentials"] == "true" and "Origin" in r.headers["Vary"]
    assert "X-Request-ID" in r.headers["Access-Control-Expose-Headers"]


def test_cors_origem_desconhecida_ou_ausente_nao_recebe_cabecalhos(client):
    assert "Access-Control-Allow-Origin" not in client.get(
        "/api/produtos", headers={"Origin": "https://malicioso.example"}).headers
    assert "Access-Control-Allow-Origin" not in client.get("/api/produtos").headers


def test_cors_preflight_em_dev_reflete_os_headers_pedidos(client):
    r = client.options("/api/pedidos", headers={
        "Origin": "http://localhost:4200", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,idempotency-key"})
    assert r.status_code == 200
    assert r.headers["Access-Control-Allow-Headers"] == "authorization,idempotency-key"
    assert "POST" in r.headers["Access-Control-Allow-Methods"] and r.headers["Access-Control-Max-Age"] == "3600"


def test_cors_em_producao_so_aceita_as_origens_informadas(tmp_path):
    cliente = app_prod(tmp_path).test_client()
    pedido = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-qualquer"}
    ok = cliente.options("/api/pedidos", headers={"Origin": "https://app.exemplo.com.br", **pedido})
    assert ok.headers["Access-Control-Allow-Origin"] == "https://app.exemplo.com.br"
    assert ok.headers["Access-Control-Allow-Headers"] == "Authorization, Content-Type, Idempotency-Key, X-Request-ID"
    assert "Access-Control-Allow-Origin" not in cliente.options(
        "/api/pedidos", headers={"Origin": "http://localhost:3000", **pedido}).headers


# ============================== perfis e configuração ================================
def test_prod_exige_variaveis_obrigatorias():
    with pytest.raises(RuntimeError, match="JWT_SECRET, DB_PATH"):
        Settings.carregar(env={"APP_PROFILE": "prod"})
    with pytest.raises(RuntimeError, match="DB_PATH"):
        Settings.carregar(env={"APP_PROFILE": "prod", "JWT_SECRET": "x" * 40})


def test_prod_rejeita_segredo_de_desenvolvimento_e_segredo_curto():
    env = {"APP_PROFILE": "prod", "DB_PATH": "/tmp/x.db"}
    with pytest.raises(RuntimeError, match="desenvolvimento"):
        Settings.carregar(env={**env, "JWT_SECRET": SEGREDO_DEV})
    with pytest.raises(RuntimeError, match="32 caracteres"):
        Settings.carregar(env={**env, "JWT_SECRET": "curto"})


def test_padroes_de_cada_perfil():
    dev = Settings.carregar(env={})
    assert dev.profile == "dev" and dev.docs_enabled and dev.simulacao_header_habilitada and dev.seed_enabled
    assert dev.pagamento_forcar_status == "APROVADO" and "http://localhost:3000" in dev.cors_allowed_origins
    prod = Settings.carregar(env={"APP_PROFILE": "prod", "JWT_SECRET": "x" * 40, "DB_PATH": "/tmp/x.db"})
    assert not prod.docs_enabled and not prod.simulacao_header_habilitada and not prod.seed_enabled
    assert prod.pagamento_forcar_status == "" and prod.cors_allowed_origins == ()
    assert "*" not in prod.cors_allowed_headers


def test_variaveis_de_ambiente_sao_lidas():
    cfg = Settings.carregar(env={
        "CORS_ALLOWED_ORIGINS": "https://a.com, https://b.com", "JWT_EXPIRATION_MINUTES": "15",
        "PAGAMENTO_FORCAR_STATUS": "recusado", "PAGAMENTO_FORCAR_STATUS_ESTORNO": "indisponivel",
        "SERVER_PORT": "9090", "SEED_ENABLED": "false", "TERMO_FIDELIDADE_VERSAO": "3.0"})
    assert cfg.cors_allowed_origins == ("https://a.com", "https://b.com") and cfg.jwt_expiration_minutes == 15
    assert (cfg.pagamento_forcar_status, cfg.pagamento_forcar_status_estorno) == ("RECUSADO", "INDISPONIVEL")
    assert (cfg.server_port, cfg.seed_enabled, cfg.termo_fidelidade_versao) == (9090, False, "3.0")


@pytest.mark.parametrize("env", [{"PAGAMENTO_FORCAR_STATUS": "TALVEZ"},
                                 {"PAGAMENTO_FORCAR_STATUS_ESTORNO": "RECUSADO"},
                                 {"APP_PROFILE": "staging"}])
def test_configuracoes_invalidas_impedem_a_inicializacao(env):
    with pytest.raises(RuntimeError):
        Settings.carregar(env=env)


def test_documento_legal_vigente_inexistente_impede_a_inicializacao():
    with pytest.raises(RuntimeError, match="não encontrado"):
        create_app(configuracao(termos_uso_versao="9.9"))


def test_producao_nao_cria_dados_de_demonstracao(tmp_path):
    cliente = app_prod(tmp_path).test_client()
    r = cliente.post("/api/auth/login", json={"email": "admin@raizes.com", "senha": "admin123"})
    assert r.status_code == 401


# ================================== JWT e senhas =====================================
def test_tokens_invalidos_sao_rejeitados(app, client):
    segredo = app.extensions["settings"].jwt_secret
    futuro = datetime.now(timezone.utc) + timedelta(minutes=5)
    passado = datetime.now(timezone.utc) - timedelta(minutes=1)
    invalidos = {
        "expirado": jwt.encode({"sub": "1", "exp": passado}, segredo, algorithm="HS256"),
        "outro segredo": jwt.encode({"sub": "1", "exp": futuro}, "outro-segredo-" + "x" * 30, algorithm="HS256"),
        "sem exp": jwt.encode({"sub": "1"}, segredo, algorithm="HS256"),
        "sem sub": jwt.encode({"exp": futuro}, segredo, algorithm="HS256"),
        "alg none": jwt.encode({"sub": "1", "exp": futuro}, None, algorithm="none"),
        "usuario inexistente": jwt.encode({"sub": "999", "exp": futuro}, segredo, algorithm="HS256"),
    }
    for nome, token in invalidos.items():
        r = client.get("/api/pedidos", headers={"Authorization": f"Bearer {token}"})
        assert (r.status_code, r.get_json()["error"]) == (401, "TOKEN_INVALIDO"), nome
    valido = jwt.encode({"sub": "1", "exp": futuro}, segredo, algorithm="HS256")
    assert client.get("/api/pedidos", headers={"Authorization": f"Bearer {valido}"}).status_code == 200
    assert client.get("/api/pedidos", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/pedidos", headers={"Authorization": "Bearer "}).status_code == 401


def test_token_emitido_pela_api_expira_apos_o_prazo(app, client):
    app.extensions["relogio"] = lambda: datetime.now(timezone.utc) - timedelta(hours=2)
    token = client.post("/api/auth/login", json={"email": "cliente@raizes.com", "senha": "cliente123"}).get_json()
    del app.extensions["relogio"]
    assert token["tipo"] == "Bearer" and token["expiraEmSegundos"] == 3600
    r = client.get("/api/pedidos", headers={"Authorization": f"Bearer {token['token']}"})
    assert (r.status_code, r.get_json()["error"]) == (401, "TOKEN_INVALIDO")


def test_senhas_sao_armazenadas_com_hash_e_salt(app):
    conn = sqlite3.connect(app.extensions["settings"].db_path)
    hashes = [linha[0] for linha in conn.execute("SELECT senha_hash FROM usuarios")]
    conn.close()
    assert len(hashes) == 5 and all(h.startswith("pbkdf2_sha256$") for h in hashes)
    assert not any(s in h for h in hashes for s in ("cliente123", "admin123"))
    a, b = senhas.gerar_hash("mesma-senha", 1000), senhas.gerar_hash("mesma-senha", 1000)
    assert a != b                                                        # salt diferente a cada hash
    assert senhas.verificar("mesma-senha", a) and not senhas.verificar("outra-senha", a)
    assert not senhas.verificar("x", "formato-invalido")


def test_respostas_nunca_expoem_senha_ou_hash(api):
    texto = api("GET", "/api/usuarios", "admin").get_data(as_text=True).lower()
    assert "pbkdf2" not in texto and "senha" not in texto and "cliente123" not in texto
    cadastro = api("POST", "/api/auth/login", json={"email": "cliente@raizes.com", "senha": "cliente123"})
    assert set(cadastro.get_json()) == {"token", "tipo", "expiraEmSegundos"}


# ================================ migrations e seed ==================================
def test_migrations_sao_idempotentes_e_validam_o_checksum(tmp_path):
    conn = database.abrir_conexao(str(tmp_path / "m.db"))
    assert database.migrar(conn) == [1]
    assert database.migrar(conn) == []
    conn.execute("UPDATE historico_migracoes SET checksum='adulterado' WHERE versao=1")
    with pytest.raises(RuntimeError, match="V1"):
        database.migrar(conn)


def test_limpar_so_funciona_fora_de_producao(tmp_path):
    conn = database.abrir_conexao(str(tmp_path / "l.db"))
    database.migrar(conn)
    with pytest.raises(RuntimeError, match="prod"):
        database.limpar(conn, "prod")
    assert conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0           # nada foi apagado
    assert database.limpar(conn, "dev") > 10
    assert conn.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall() == []
    assert database.migrar(conn) == [1]                                                 # recriável


def test_comandos_de_cli_de_banco(tmp_path):
    runner = create_app(configuracao()).test_cli_runner()
    assert "nenhuma pendente" in runner.invoke(args=["db-migrar"]).output
    assert "Objetos removidos" in runner.invoke(args=["db-limpar"]).output
    bloqueado = app_prod(tmp_path).test_cli_runner().invoke(args=["db-limpar"])
    assert bloqueado.exit_code != 0 and isinstance(bloqueado.exception, RuntimeError)


def test_seed_cria_os_dados_de_demonstracao_uma_unica_vez(app):
    conn = sqlite3.connect(app.extensions["settings"].db_path)
    contagens = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
        "unidades", "usuarios", "produtos", "estoques", "campanhas", "cupons")}
    assert contagens == {"unidades": 2, "usuarios": 5, "produtos": 4, "estoques": 8, "campanhas": 1, "cupons": 2}
    create_app(app.extensions["settings"])                                              # segunda inicialização
    assert conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 5
    conn.close()


def test_sem_seed_o_banco_comeca_vazio():
    cliente = create_app(configuracao(seed_enabled=False)).test_client()
    assert cliente.get("/api/produtos").get_json()["totalElements"] == 0


# =============================== utilitários e docs ==================================
def test_pseudonimizacao_e_estavel_e_nao_revela_o_identificador():
    p = pseudonimizar("Cliente@Raizes.com")
    assert p == pseudonimizar("  cliente@raizes.com ") and p.startswith("u_") and "raizes" not in p
    assert p != pseudonimizar("outro@raizes.com")
    assert pseudonimizar(None) == pseudonimizar("") == "anonimo"


def test_swagger_e_contrato_disponiveis_em_dev(client):
    spec = client.get("/api/v3/api-docs").get_json()
    assert spec["openapi"] == "3.1.0" and spec["servers"] == [{"url": "/api"}]
    yaml = client.get("/api/v3/api-docs.yaml")
    assert yaml.status_code == 200 and "openapi: 3.1.0" in yaml.get_data(as_text=True)
    assert b"SwaggerUIBundle" in client.get("/api/swagger-ui.html").data


def test_swagger_e_contrato_indisponiveis_em_producao(tmp_path):
    cliente = app_prod(tmp_path).test_client()
    for caminho in ("/api/v3/api-docs", "/api/v3/api-docs.yaml", "/api/swagger-ui.html"):
        assert cliente.get(caminho).status_code == 404
