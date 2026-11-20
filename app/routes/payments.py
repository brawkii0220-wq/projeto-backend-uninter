import json
from fastapi import APIRouter,Depends,HTTPException
from app.database import db
from app.schemas.models import Payment
from app.security.auth import current
from app.gateways.payment_mock import MockGateway
router=APIRouter(tags=["Pagamento mock"])
@router.post("/pedidos/{oid}/pagamento")
def pay(oid:str,x:Payment,u=Depends(current)):
    with db() as c:
        o=c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
        if not o: raise HTTPException(404,"Pedido não encontrado")
        if o["user_id"]!=u["id"] and u["role"] not in {"ADMIN","GERENTE","ATENDENTE"}: raise HTTPException(403,"Sem acesso")
        if o["status"]=="CANCELADO": raise HTTPException(409,"Pedido cancelado")
        pid,req,res=MockGateway().request(oid,o["total"],x.forma_pagamento)
        c.execute("INSERT INTO payments(id,order_id,status,amount,request,response) VALUES(?,?,?,?,?,?)",(pid,oid,"pending",o["total"],json.dumps(req),json.dumps(res)))
    return {"payment_id":pid,"status":"pending","request_payload":req,"provider_response":res,
            "client_message":"Pagamento simulado. Nenhuma cobrança real foi feita."}
@router.get("/pedidos/{oid}/pagamento/tentativas")
def attempts(oid:str,u=Depends(current)):
    with db() as c:
        o=c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
        if not o: raise HTTPException(404,"Pedido não encontrado")
        if o["user_id"]!=u["id"] and u["role"] not in {"ADMIN","GERENTE","ATENDENTE"}: raise HTTPException(403,"Sem acesso")
        rows=c.execute("SELECT * FROM payments WHERE order_id=?",(oid,)).fetchall()
    return [{"id":r["id"],"status":r["status"],"request":json.loads(r["request"]),"response":json.loads(r["response"])} for r in rows]
