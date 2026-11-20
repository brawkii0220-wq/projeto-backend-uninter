# Projeto back end - Raizes do Nordeste
API de pedidos para restaurante (App / Totem / Web)
---------------------------------------------------
Demonstração educacional com FastAPI + SQLite.

Instalação:
    pip install -r requirements.txt

Execução:
    uvicorn restaurante_api:app --reload

Documentação interativa:
    http://127.0.0.1:8000/docs

Usuário administrador inicial:
    email: admin@demo.com
    senha: Admin123!

IMPORTANTE:
- O pagamento é MOCK. Nenhuma cobrança real é feita.
- Troque SECRET_KEY e a senha inicial antes de qualquer uso real.
- Para produção, use HTTPS, gestão de segredos, migrations, rate limiting,
  logs/auditoria, testes, política de privacidade e um provedor de identidade.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional
import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid

from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr, Field


DB_PATH = "restaurante.db"
SECRET_KEY = "TROQUE-ESTA-CHAVE-ANTES-DE-USAR"
TOKEN_HOURS = 12

app = FastAPI(
    title="API de Pedidos - Restaurante",
    description="Cadastro, cardápio, pedidos, estoque, fidelidade, campanhas e pagamento simulado.",
    version="1.0.0",
)


# ----------------------------- Banco de dados -----------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'cliente',
            loyalty_consent INTEGER NOT NULL DEFAULT 0,
            points INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id INTEGER NOT NULL REFERENCES units(id),
            name TEXT NOT NULL,
            description TEXT,
            price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            unit_id INTEGER NOT NULL REFERENCES units(id),
            status TEXT NOT NULL,
            subtotal_cents INTEGER NOT NULL,
            discount_cents INTEGER NOT NULL DEFAULT 0,
            total_cents INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL REFERENCES orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price_cents INTEGER NOT NULL,
            total_cents INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            movement_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS loyalty_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            points INTEGER NOT NULL,
            description TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            discount_percent INTEGER NOT NULL,
            min_order_cents INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            starts_at TEXT,
            ends_at TEXT
        );
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL REFERENCES orders(id),
            provider TEXT NOT NULL,
            status TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            request_payload TEXT NOT NULL,
            response_payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)

        if not con.execute("SELECT 1 FROM users WHERE email = ?", ("admin@demo.com",)).fetchone():
            con.execute(
                """INSERT INTO users(name,email,password_hash,role,created_at)
                   VALUES(?,?,?,?,?)""",
                ("Administrador", "admin@demo.com", hash_password("Admin123!"),
                 "admin", now()),
            )
        if not con.execute("SELECT 1 FROM units LIMIT 1").fetchone():
            cur = con.execute("INSERT INTO units(name,address) VALUES(?,?)",
                              ("Unidade Centro", "Rua Exemplo, 100"))
            unit_id = cur.lastrowid
            con.executemany(
                """INSERT INTO products(unit_id,name,description,price_cents,stock)
                   VALUES(?,?,?,?,?)""",
                [
                    (unit_id, "Hambúrguer clássico", "Pão, carne, queijo e salada", 2490, 20),
                    (unit_id, "Batata frita", "Porção média", 1290, 30),
                    (unit_id, "Refrigerante", "Lata 350 ml", 600, 40),
                ],
            )
        if not con.execute("SELECT 1 FROM campaigns WHERE code='BEMVINDO'").fetchone():
            con.execute(
                """INSERT INTO campaigns(code,description,discount_percent,min_order_cents,active)
                   VALUES(?,?,?,?,1)""",
                ("BEMVINDO", "Desconto demonstrativo de boas-vindas", 10, 3000),
            )


def now():
    return datetime.now(timezone.utc).isoformat()


# ----------------------------- Autenticação -------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()
        return hmac.compare_digest(actual, expected)
    except ValueError:
        return False


def make_token(user_id: int, role: str) -> str:
    # Token assinado simples para demonstração; em produção prefira OAuth2/JWT
    # com biblioteca consolidada, expiração e rotação de chaves.
    payload = json.dumps({
        "sub": user_id,
        "role": role,
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)).timestamp())
    }, separators=(",", ":")).encode()
    body = secrets.token_urlsafe(8) + "." + payload.hex()
    signature = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + signature


def read_token(token: str):
    try:
        nonce, payload_hex, signature = token.split(".")
        body = nonce + "." + payload_hex
        expected = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload = json.loads(bytes.fromhex(payload_hex))
        if payload["exp"] < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError()
        return payload
    except Exception:
        raise HTTPException(401, "Token inválido ou expirado")


def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Envie Authorization: Bearer <token>")
    payload = read_token(authorization[7:])
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE id=?", (payload["sub"],)).fetchone()
    if not user:
        raise HTTPException(401, "Usuário não encontrado")
    return dict(user)


def require_roles(*roles):
    def dependency(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Você não tem permissão para esta operação")
        return user
    return dependency


# -------------------------------- Schemas ---------------------------------

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)
    loyalty_consent: bool = False


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserRoleIn(BaseModel):
    role: str


class ProductIn(BaseModel):
    unit_id: int
    name: str
    description: str = ""
    price_cents: int = Field(ge=0)
    stock: int = Field(ge=0)


class OrderLineIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=50)


class OrderIn(BaseModel):
    unit_id: int
    items: list[OrderLineIn] = Field(min_length=1)
    campaign_code: Optional[str] = None


class StatusIn(BaseModel):
    status: str


class StockIn(BaseModel):
    product_id: int
    movement_type: str  # entrada ou saida
    quantity: int = Field(gt=0)
    reason: str = ""


class RedeemIn(BaseModel):
    points: int = Field(gt=0)


class CampaignIn(BaseModel):
    code: str
    description: str
    discount_percent: int = Field(ge=1, le=100)
    min_order_cents: int = Field(default=0, ge=0)


class PaymentIn(BaseModel):
    method: str = Field(description="Ex.: pix, cartao ou dinheiro. Não processa cobrança real.")


# -------------------------------- Helpers ---------------------------------

def money(cents: int) -> str:
    return f"R$ {cents / 100:.2f}".replace(".", ",")


def get_order(con, order_id):
    row = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Pedido não encontrado")
    result = dict(row)
    result["items"] = [dict(x) for x in con.execute(
        "SELECT * FROM order_items WHERE order_id=?", (order_id,)
    ).fetchall()]
    return result


def apply_campaign(con, code, subtotal):
    if not code:
        return 0
    campaign = con.execute(
        "SELECT * FROM campaigns WHERE code=? AND active=1", (code.upper(),)
    ).fetchone()
    if not campaign:
        raise HTTPException(400, "Cupom inexistente ou inativo")
    if subtotal < campaign["min_order_cents"]:
        raise HTTPException(400, "Pedido não atingiu o valor mínimo da campanha")
    discount = int((Decimal(subtotal) * Decimal(campaign["discount_percent"]) / 100)
                   .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return min(discount, subtotal)


# ------------------------------ Inicialização -----------------------------

init_db()


@app.get("/")
def health():
    return {"servico": "API de Pedidos", "status": "online", "docs": "/docs"}


# --------------------------- Cadastro e usuários --------------------------

@app.post("/auth/register", status_code=201)
def register(data: RegisterIn):
    with db() as con:
        try:
            cur = con.execute(
                """INSERT INTO users(name,email,password_hash,role,loyalty_consent,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (data.name, data.email.lower(), hash_password(data.password), "cliente",
                 int(data.loyalty_consent), now()),
            )
            user_id = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Este e-mail já está cadastrado")
    return {"id": user_id, "email": data.email.lower(), "role": "cliente",
            "loyalty_consent": data.loyalty_consent}


@app.post("/auth/login")
def login(data: LoginIn):
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE email=?", (data.email.lower(),)).fetchone()
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(401, "E-mail ou senha incorretos")
    token = make_token(user["id"], user["role"])
    return {"access_token": token, "token_type": "bearer", "expires_in_hours": TOKEN_HOURS,
            "user": {"id": user["id"], "name": user["name"], "role": user["role"]}}


@app.get("/users/me")
def me(user=Depends(current_user)):
    return {"id": user["id"], "name": user["name"], "email": user["email"],
            "role": user["role"], "points": user["points"],
            "loyalty_consent": bool(user["loyalty_consent"])}


@app.patch("/admin/users/{user_id}/role")
def change_role(user_id: int, data: UserRoleIn,
                admin=Depends(require_roles("admin"))):
    if data.role not in ("cliente", "cozinha", "atendente", "gerente", "admin"):
        raise HTTPException(400, "Perfil inválido")
    with db() as con:
        cur = con.execute("UPDATE users SET role=? WHERE id=?", (data.role, user_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Usuário não encontrado")
    return {"user_id": user_id, "role": data.role}


# ------------------------------ Unidades/menu ------------------------------

@app.get("/units")
def list_units():
    with db() as con:
        return [dict(x) for x in con.execute("SELECT * FROM units").fetchall()]


@app.get("/units/{unit_id}/menu")
def menu(unit_id: int, available_only: bool = True):
    with db() as con:
        if not con.execute("SELECT 1 FROM units WHERE id=?", (unit_id,)).fetchone():
            raise HTTPException(404, "Unidade não encontrada")
        sql = """SELECT id,unit_id,name,description,price_cents,stock,active
                 FROM products WHERE unit_id=? AND active=1"""
        rows = con.execute(sql, (unit_id,)).fetchall()
    products = [dict(x) for x in rows]
    if available_only:
        products = [p for p in products if p["stock"] > 0]
    for p in products:
        p["price"] = money(p["price_cents"])
        p["available"] = p["stock"] > 0
    return {"unit_id": unit_id, "items": products}


@app.post("/admin/products", status_code=201)
def create_product(data: ProductIn, user=Depends(require_roles("admin", "gerente"))):
    with db() as con:
        if not con.execute("SELECT 1 FROM units WHERE id=?", (data.unit_id,)).fetchone():
            raise HTTPException(404, "Unidade não encontrada")
        cur = con.execute(
            """INSERT INTO products(unit_id,name,description,price_cents,stock)
               VALUES(?,?,?,?,?)""",
            (data.unit_id, data.name, data.description, data.price_cents, data.stock),
        )
        product_id = cur.lastrowid
        if data.stock:
            con.execute(
                """INSERT INTO stock_movements(product_id,movement_type,quantity,reason,created_at)
                   VALUES(?,?,?,?,?)""",
                (product_id, "entrada", data.stock, "Estoque inicial", now()),
            )
    return {"product_id": product_id}


# --------------------------------- Pedidos ---------------------------------

@app.post("/orders", status_code=201)
def create_order(data: OrderIn, user=Depends(current_user)):
    with db() as con:
        if not con.execute("SELECT 1 FROM units WHERE id=?", (data.unit_id,)).fetchone():
            raise HTTPException(404, "Unidade não encontrada")

        # Agrupa IDs repetidos para validar e baixar estoque corretamente.
        quantities = {}
        for line in data.items:
            quantities[line.product_id] = quantities.get(line.product_id, 0) + line.quantity

        items = []
        subtotal = 0
        for product_id, quantity in quantities.items():
            product = con.execute(
                """SELECT * FROM products
                   WHERE id=? AND unit_id=? AND active=1""",
                (product_id, data.unit_id),
            ).fetchone()
            if not product:
                raise HTTPException(400, f"Produto {product_id} não pertence à unidade ou está inativo")
            if product["stock"] < quantity:
                raise HTTPException(409, f"Estoque insuficiente para {product['name']}")
            line_total = product["price_cents"] * quantity
            subtotal += line_total
            items.append((product, quantity, line_total))

        discount = apply_campaign(con, data.campaign_code, subtotal)
        total = subtotal - discount
        order_id = str(uuid.uuid4())
        con.execute(
            """INSERT INTO orders(id,user_id,unit_id,status,subtotal_cents,discount_cents,total_cents,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (order_id, user["id"], data.unit_id, "cozinha", subtotal, discount, total, now()),
        )
        for product, quantity, line_total in items:
            con.execute(
                """INSERT INTO order_items(order_id,product_id,product_name,quantity,
                                           unit_price_cents,total_cents)
                   VALUES(?,?,?,?,?,?)""",
                (order_id, product["id"], product["name"], quantity,
                 product["price_cents"], line_total),
            )
            con.execute("UPDATE products SET stock=stock-? WHERE id=?",
                        (quantity, product["id"]))
            con.execute(
                """INSERT INTO stock_movements(product_id,movement_type,quantity,reason,created_at)
                   VALUES(?,?,?,?,?)""",
                (product["id"], "saida", quantity, f"Pedido {order_id}", now()),
            )

        # Pontos: 1 ponto por R$ 1 pago, somente com consentimento explícito.
        if user["loyalty_consent"]:
            earned = total // 100
            if earned:
                con.execute("UPDATE users SET points=points+? WHERE id=?",
                            (earned, user["id"]))
                con.execute(
                    """INSERT INTO loyalty_ledger(user_id,points,description,created_at)
                       VALUES(?,?,?,?)""",
                    (user["id"], earned, f"Pontos pelo pedido {order_id}", now()),
                )

        result = get_order(con, order_id)
    result["subtotal"] = money(subtotal)
    result["discount"] = money(discount)
    result["total"] = money(total)
    return result


@app.get("/orders/{order_id}")
def order_details(order_id: str, user=Depends(current_user)):
    with db() as con:
        order = get_order(con, order_id)
    if user["role"] not in ("admin", "gerente", "cozinha", "atendente") and order["user_id"] != user["id"]:
        raise HTTPException(403, "Este pedido pertence a outro usuário")
    order["total"] = money(order["total_cents"])
    return order


@app.get("/orders")
def list_orders(status: Optional[str] = None, user=Depends(current_user)):
    with db() as con:
        if user["role"] in ("admin", "gerente", "cozinha", "atendente"):
            if status:
                rows = con.execute("SELECT * FROM orders WHERE status=? ORDER BY created_at DESC",
                                   (status,)).fetchall()
            else:
                rows = con.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
        else:
            if status:
                rows = con.execute(
                    "SELECT * FROM orders WHERE user_id=? AND status=? ORDER BY created_at DESC",
                    (user["id"], status)).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC",
                    (user["id"],)).fetchall()
    return [dict(x) for x in rows]


@app.patch("/orders/{order_id}/status")
def update_order_status(order_id: str, data: StatusIn,
                        user=Depends(require_roles("admin", "gerente", "cozinha", "atendente"))):
    allowed = {"cozinha", "pronto", "entregue", "cancelado"}
    if data.status not in allowed:
        raise HTTPException(400, f"Status permitido: {', '.join(sorted(allowed))}")
    with db() as con:
        order = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(404, "Pedido não encontrado")
        current = order["status"]
        transitions = {
            "cozinha": {"pronto", "cancelado"},
            "pronto": {"entregue", "cancelado"},
            "entregue": set(),
            "cancelado": set(),
        }
        if data.status not in transitions.get(current, set()):
            raise HTTPException(409, f"Transição inválida: {current} -> {data.status}")
        con.execute("UPDATE orders SET status=? WHERE id=?", (data.status, order_id))
        # Se cancelado antes da entrega, devolve as quantidades ao estoque.
        if data.status == "cancelado":
            lines = con.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchall()
            for line in lines:
                con.execute("UPDATE products SET stock=stock+? WHERE id=?",
                            (line["quantity"], line["product_id"]))
                con.execute(
                    """INSERT INTO stock_movements(product_id,movement_type,quantity,reason,created_at)
                       VALUES(?,?,?,?,?)""",
                    (line["product_id"], "entrada", line["quantity"],
                     f"Estorno do pedido cancelado {order_id}", now()),
                )
    return {"order_id": order_id, "previous_status": current, "status": data.status}


# --------------------------------- Estoque ---------------------------------

@app.post("/admin/stock/movements")
def stock_movement(data: StockIn, user=Depends(require_roles("admin", "gerente"))):
    if data.movement_type not in ("entrada", "saida"):
        raise HTTPException(400, "movement_type deve ser entrada ou saida")
    with db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (data.product_id,)).fetchone()
        if not product:
            raise HTTPException(404, "Produto não encontrado")
        new_stock = product["stock"] + data.quantity if data.movement_type == "entrada" else product["stock"] - data.quantity
        if new_stock < 0:
            raise HTTPException(409, "Estoque insuficiente para esta saída")
        con.execute("UPDATE products SET stock=? WHERE id=?", (new_stock, data.product_id))
        con.execute(
            """INSERT INTO stock_movements(product_id,movement_type,quantity,reason,created_at)
               VALUES(?,?,?,?,?)""",
            (data.product_id, data.movement_type, data.quantity, data.reason, now()),
        )
    return {"product_id": data.product_id, "stock": new_stock}


@app.get("/admin/stock")
def stock_report(user=Depends(require_roles("admin", "gerente"))):
    with db() as con:
        rows = con.execute(
            """SELECT p.id,p.name,p.unit_id,p.stock,
                      COALESCE(SUM(CASE WHEN sm.movement_type='entrada' THEN sm.quantity
                                        ELSE -sm.quantity END),0) AS net_movements
               FROM products p LEFT JOIN stock_movements sm ON sm.product_id=p.id
               GROUP BY p.id ORDER BY p.name"""
        ).fetchall()
    return [dict(x) for x in rows]


# ------------------------------- Fidelidade -------------------------------

@app.post("/loyalty/consent")
def set_loyalty_consent(consent: bool, user=Depends(current_user)):
    with db() as con:
        con.execute("UPDATE users SET loyalty_consent=? WHERE id=?",
                    (int(consent), user["id"]))
    return {"loyalty_consent": consent}


@app.get("/loyalty/balance")
def loyalty_balance(user=Depends(current_user)):
    if not user["loyalty_consent"]:
        raise HTTPException(403, "É necessário consentir com o programa de fidelidade")
    with db() as con:
        entries = [dict(x) for x in con.execute(
            "SELECT points,description,created_at FROM loyalty_ledger WHERE user_id=? ORDER BY id DESC",
            (user["id"],)).fetchall()]
    return {"points": user["points"], "ledger": entries}


@app.post("/loyalty/redeem")
def redeem_points(data: RedeemIn, user=Depends(current_user)):
    if not user["loyalty_consent"]:
        raise HTTPException(403, "É necessário consentir com o programa de fidelidade")
    if data.points < 100:
        raise HTTPException(400, "O resgate mínimo é de 100 pontos")
    with db() as con:
        fresh = con.execute("SELECT points FROM users WHERE id=?", (user["id"],)).fetchone()
        if fresh["points"] < data.points:
            raise HTTPException(409, "Saldo de pontos insuficiente")
        con.execute("UPDATE users SET points=points-? WHERE id=?", (data.points, user["id"]))
        con.execute(
            """INSERT INTO loyalty_ledger(user_id,points,description,created_at)
               VALUES(?,?,?,?)""",
            (user["id"], -data.points, "Resgate de pontos: benefício concedido fora da API", now()),
        )
    # Regra ilustrativa: 100 pontos = R$ 5,00 de crédito. A aplicação do crédito
    # no pedido deve ser validada e integrada ao checkout em uma versão de produção.
    return {"redeemed_points": data.points, "illustrative_credit": money((data.points // 100) * 500),
            "message": "Resgate registrado. Conceda o benefício conforme as regras da loja."}


# --------------------------- Campanhas / promoções ------------------------

@app.post("/admin/campaigns", status_code=201)
def create_campaign(data: CampaignIn, user=Depends(require_roles("admin", "gerente"))):
    with db() as con:
        try:
            cur = con.execute(
                """INSERT INTO campaigns(code,description,discount_percent,min_order_cents,active)
                   VALUES(?,?,?,?,1)""",
                (data.code.upper(), data.description, data.discount_percent, data.min_order_cents),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Código de campanha já existe")
    return {"campaign_id": cur.lastrowid, "code": data.code.upper()}


@app.get("/campaigns")
def list_campaigns():
    with db() as con:
        rows = con.execute(
            """SELECT code,description,discount_percent,min_order_cents
               FROM campaigns WHERE active=1"""
        ).fetchall()
    return [dict(x) for x in rows]


# Regra aplicada no checkout:
# 1) cliente informa campaign_code no POST /orders;
# 2) API verifica se existe e está ativa;
# 3) verifica subtotal mínimo;
# 4) calcula percentual sobre o subtotal e limita desconto ao subtotal;
# 5) grava subtotal, desconto e total no pedido.
# Extensões sugeridas: validade, limite de uso, público elegível, unidade,
# dias/horários, produtos participantes e combinação de cupons.


# -------------------------- Pagamento externo MOCK -------------------------

@app.post("/orders/{order_id}/payments")
def request_mock_payment(order_id: str, data: PaymentIn, user=Depends(current_user)):
    with db() as con:
        order = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(404, "Pedido não encontrado")
        if user["role"] not in ("admin", "gerente", "atendente") and order["user_id"] != user["id"]:
            raise HTTPException(403, "Este pedido pertence a outro usuário")
        if order["status"] == "cancelado":
            raise HTTPException(409, "Não é possível pagar um pedido cancelado")

        payment_id = str(uuid.uuid4())
        request_payload = {
            "payment_id": payment_id,
            "order_id": order_id,
            "amount_cents": order["total_cents"],
            "currency": "BRL",
            "method": data.method,
            "callback_url": "/payments/mock/callback",
        }

        # Simulação determinística de retorno do provedor.
        # O status "pending" representa aguardando confirmação; nenhum dinheiro
        # é movimentado e nenhum dado de cartão é coletado.
        response_payload = {
            "provider_reference": "MOCK-" + payment_id[:8].upper(),
            "status": "pending",
            "message": "Solicitação simulada recebida. Aguardando confirmação fictícia.",
            "test_mode": True,
        }
        con.execute(
            """INSERT INTO payments(id,order_id,provider,status,amount_cents,
                                    request_payload,response_payload,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (payment_id, order_id, "mock-provider", "pending", order["total_cents"],
             json.dumps(request_payload), json.dumps(response_payload), now()),
        )

    # Este é o contrato de resposta que App/Totem/Web pode consumir.
    return {
        "payment_id": payment_id,
        "order_id": order_id,
        "status": "pending",
        "amount": money(order["total_cents"]),
        "request_payload": request_payload,
        "provider_response": response_payload,
        "client_message": "Pagamento solicitado em ambiente de simulação.",
    }


@app.post("/payments/mock/{payment_id}/simulate-result")
def simulate_payment_result(payment_id: str, status: str,
                            user=Depends(require_roles("admin", "gerente", "atendente"))):
    if status not in ("approved", "declined", "cancelled"):
        raise HTTPException(400, "status deve ser approved, declined ou cancelled")
    with db() as con:
        payment = con.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not payment:
            raise HTTPException(404, "Pagamento não encontrado")
        response = {
            "provider_reference": "MOCK-" + payment_id[:8].upper(),
            "status": status,
            "message": "Retorno simulado do provedor externo.",
            "test_mode": True,
        }
        con.execute("UPDATE payments SET status=?,response_payload=? WHERE id=?",
                    (status, json.dumps(response), payment_id))
    return {"payment_id": payment_id, "status": status, "provider_response": response}


@app.get("/orders/{order_id}/payments")
def payment_history(order_id: str, user=Depends(current_user)):
    with db() as con:
        order = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(404, "Pedido não encontrado")
        if user["role"] not in ("admin", "gerente", "atendente") and order["user_id"] != user["id"]:
            raise HTTPException(403, "Este pedido pertence a outro usuário")
        rows = con.execute("SELECT * FROM payments WHERE order_id=? ORDER BY created_at DESC",
                           (order_id,)).fetchall()
    return [{
        "payment_id": r["id"], "provider": r["provider"], "status": r["status"],
        "amount": money(r["amount_cents"]),
        "request_payload": json.loads(r["request_payload"]),
        "response_payload": json.loads(r["response_payload"]),
        "created_at": r["created_at"],
    } for r in rows]
