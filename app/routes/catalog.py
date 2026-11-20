from fastapi import APIRouter,Depends,HTTPException
from app.database import db
from app.schemas.models import Unit,Product
from app.security.auth import current,roles
router=APIRouter(tags=["Unidades e cardápio"])
@router.get("/unidades")
def units(u=Depends(current)):
    with db() as c: return [dict(x) for x in c.execute("SELECT * FROM units WHERE active=1")]
@router.post("/unidades",status_code=201)
def add_unit(x:Unit,u=Depends(roles("ADMIN"))):
    with db() as c: cur=c.execute("INSERT INTO units(name,address) VALUES(?,?)",(x.nome,x.endereco))
    return {"id":cur.lastrowid}
@router.get("/produtos")
def products(unidade_id:int|None=None):
    with db() as c:
        sql="SELECT p.*,s.quantity estoque FROM products p JOIN stock s ON s.product_id=p.id WHERE p.active=1"
        rows=c.execute(sql+(" AND p.unit_id=?" if unidade_id else ""),((unidade_id,) if unidade_id else ())).fetchall()
    return [dict(x) for x in rows]
@router.post("/produtos",status_code=201)
def add_product(x:Product,u=Depends(roles("ADMIN","GERENTE"))):
    with db() as c:
        cur=c.execute("INSERT INTO products(unit_id,name,description,price) VALUES(?,?,?,?)",(x.unidade_id,x.nome,x.descricao,x.preco_centavos))
        c.execute("INSERT INTO stock VALUES(?,?)",(cur.lastrowid,x.estoque))
        c.execute("INSERT INTO movements(product_id,kind,quantity,before_qty,after_qty,reason) VALUES(?,'ENTRADA',?,0,?,'Cadastro')",(cur.lastrowid,x.estoque,x.estoque))
    return {"id":cur.lastrowid}
