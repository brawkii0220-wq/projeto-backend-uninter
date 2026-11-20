import uuid
from fastapi import APIRouter,Depends,HTTPException
from app.database import db
from app.schemas.models import Order,Status
from app.security.auth import current,roles
router=APIRouter(prefix="/pedidos",tags=["Pedidos"])
NEXT={"AGUARDANDO_PAGAMENTO":{"RECEBIDO","CANCELADO"},"RECEBIDO":{"EM_PREPARACAO","CANCELADO"},"EM_PREPARACAO":{"PRONTO","CANCELADO"},"PRONTO":{"ENTREGUE","CANCELADO"},"ENTREGUE":set(),"CANCELADO":set()}
@router.post("",status_code=201)
def create(x:Order,u=Depends(current)):
    if x.canal not in {"APP","TOTEM","BALCAO","PICKUP","WEB"}: raise HTTPException(422,"Canal inválido")
    oid=str(uuid.uuid4())
    with db() as c:
        selected=[]; subtotal=0
        for i in x.itens:
            p=c.execute("SELECT p.*,s.quantity estoque FROM products p JOIN stock s ON s.product_id=p.id WHERE p.id=? AND p.unit_id=? AND p.active=1",(i.produto_id,x.unidade_id)).fetchone()
            if not p: raise HTTPException(400,"Produto não disponível nesta unidade")
            if p["estoque"]<i.quantidade: raise HTTPException(409,"ESTOQUE_INSUFICIENTE")
            line=p["price"]*i.quantidade; subtotal+=line; selected.append((p,i.quantidade,line))
        discount=0
        if x.cupom:
            cp=c.execute("SELECT * FROM campaigns WHERE code=? AND active=1",(x.cupom.upper(),)).fetchone()
            if not cp or subtotal<cp["min_total"]: raise HTTPException(400,"Cupom inválido ou mínimo não atingido")
            discount=subtotal*cp["percent"]//100
        total=subtotal-discount
        c.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",(oid,u["id"],x.unidade_id,x.canal,"AGUARDANDO_PAGAMENTO",subtotal,discount,total))
        for p,q,line in selected:
            before=p["estoque"]; after=before-q
            c.execute("UPDATE stock SET quantity=? WHERE product_id=?",(after,p["id"]))
            c.execute("INSERT INTO movements(product_id,kind,quantity,before_qty,after_qty,reason) VALUES(?,'SAIDA',?,?,?,?)",(p["id"],q,before,after,"Reserva pedido "+oid))
            c.execute("INSERT INTO order_items(order_id,product_id,name,quantity,unit_price,line_total) VALUES(?,?,?,?,?,?)",(oid,p["id"],p["name"],q,p["price"],line))
        if u["loyalty"]:
            pts=total//100
            c.execute("UPDATE users SET points=points+? WHERE id=?",(pts,u["id"]))
            c.execute("INSERT INTO loyalty_events(user_id,points,description) VALUES(?,?,?)",(u["id"],pts,"Compra "+oid))
    return {"pedido_id":oid,"status":"AGUARDANDO_PAGAMENTO","subtotal_centavos":subtotal,"desconto_centavos":discount,"total_centavos":total}
@router.get("")
def list_orders(u=Depends(current)):
    with db() as c:
        if u["role"] in {"ADMIN","GERENTE","ATENDENTE","COZINHA"}: rows=c.execute("SELECT * FROM orders ORDER BY created DESC").fetchall()
        else: rows=c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created DESC",(u["id"],)).fetchall()
    return [dict(x) for x in rows]
@router.patch("/{oid}/status")
def status(oid:str,x:Status,u=Depends(roles("ADMIN","GERENTE","ATENDENTE","COZINHA"))):
    with db() as c:
        o=c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
        if not o: raise HTTPException(404,"Pedido não encontrado")
        if x.status not in NEXT.get(o["status"],set()): raise HTTPException(409,"Transição de status inválida")
        c.execute("UPDATE orders SET status=? WHERE id=?",(x.status,oid))
        if x.status=="CANCELADO" and o["status"] in {"AGUARDANDO_PAGAMENTO","RECEBIDO"}:
            for it in c.execute("SELECT * FROM order_items WHERE order_id=?",(oid,)):
                s=c.execute("SELECT quantity FROM stock WHERE product_id=?",(it["product_id"],)).fetchone()
                before=s[0]; after=before+it["quantity"]
                c.execute("UPDATE stock SET quantity=? WHERE product_id=?",(after,it["product_id"]))
                c.execute("INSERT INTO movements(product_id,kind,quantity,before_qty,after_qty,reason) VALUES(?,'ENTRADA',?,?,?,?)",(it["product_id"],it["quantity"],before,after,"Cancelamento "+oid))
    return {"pedido_id":oid,"status":x.status}
