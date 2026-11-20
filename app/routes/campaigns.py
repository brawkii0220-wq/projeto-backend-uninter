from fastapi import APIRouter,Depends,HTTPException
from app.database import db
from app.schemas.models import Campaign
from app.security.auth import roles
router=APIRouter(prefix="/campanhas",tags=["Campanhas e cupons"])
@router.get("")
def list_campaigns():
    with db() as c: return [dict(r) for r in c.execute("SELECT * FROM campaigns WHERE active=1")]
@router.post("",status_code=201)
def create(x:Campaign,u=Depends(roles("ADMIN","GERENTE"))):
    with db() as c:
        try: cur=c.execute("INSERT INTO campaigns(code,description,percent,min_total) VALUES(?,?,?,?)",(x.codigo.upper(),x.descricao,x.percentual,x.minimo_centavos))
        except Exception: raise HTTPException(409,"Código já existe")
    return {"id":cur.lastrowid,"codigo":x.codigo.upper()}
@router.delete("/{cid}")
def deactivate(cid:int,u=Depends(roles("ADMIN","GERENTE"))):
    with db() as c: cur=c.execute("UPDATE campaigns SET active=0 WHERE id=?",(cid,))
    if not cur.rowcount: raise HTTPException(404,"Campanha não encontrada")
    return {"ativa":False}
