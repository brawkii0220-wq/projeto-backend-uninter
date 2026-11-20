from fastapi import APIRouter,Depends,HTTPException
from app.database import db
from app.schemas.models import Movement
from app.security.auth import roles
router=APIRouter(prefix="/estoque",tags=["Estoque"])
@router.post("/{product_id}/movimentacoes")
def move(product_id:int,x:Movement,u=Depends(roles("ADMIN","GERENTE"))):
    if x.tipo not in {"ENTRADA","SAIDA"}: raise HTTPException(422,"Tipo deve ser ENTRADA ou SAIDA")
    with db() as c:
        r=c.execute("SELECT quantity FROM stock WHERE product_id=?",(product_id,)).fetchone()
        if not r: raise HTTPException(404,"Produto sem estoque cadastrado")
        before=r[0]; after=before+x.quantidade if x.tipo=="ENTRADA" else before-x.quantidade
        if after<0: raise HTTPException(409,"Estoque insuficiente")
        c.execute("UPDATE stock SET quantity=? WHERE product_id=?",(after,product_id))
        c.execute("INSERT INTO movements(product_id,kind,quantity,before_qty,after_qty,reason) VALUES(?,?,?,?,?,?)",(product_id,x.tipo,x.quantidade,before,after,x.motivo))
    return {"saldo_anterior":before,"saldo_atual":after}
@router.get("/{product_id}/movimentacoes")
def history(product_id:int,u=Depends(roles("ADMIN","GERENTE"))):
    with db() as c: return [dict(r) for r in c.execute("SELECT * FROM movements WHERE product_id=? ORDER BY id DESC",(product_id,))]
