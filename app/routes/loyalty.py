from fastapi import APIRouter,Depends,HTTPException
from app.database import db
from app.schemas.models import Redeem
from app.security.auth import current
router=APIRouter(prefix="/fidelidade",tags=["Fidelidade"])
@router.post("/consentimento")
def consent(aceitar:bool,u=Depends(current)):
    with db() as c: c.execute("UPDATE users SET loyalty=? WHERE id=?",(int(aceitar),u["id"]))
    return {"consentimento":aceitar}
@router.get("/saldo")
def balance(u=Depends(current)):
    if not u["loyalty"]: raise HTTPException(403,"Consentimento não concedido")
    return {"pontos":u["points"]}
@router.post("/resgate")
def redeem(x:Redeem,u=Depends(current)):
    if not u["loyalty"]: raise HTTPException(403,"Consentimento não concedido")
    with db() as c:
        fresh=c.execute("SELECT points FROM users WHERE id=?",(u["id"],)).fetchone()
        if x.pontos<100 or fresh[0]<x.pontos: raise HTTPException(409,"Resgate mínimo 100 pontos ou saldo insuficiente")
        c.execute("UPDATE users SET points=points-? WHERE id=?",(x.pontos,u["id"]))
        c.execute("INSERT INTO loyalty_events(user_id,points,description) VALUES(?,?,?)",(u["id"],-x.pontos,"Resgate"))
    return {"pontos_resgatados":x.pontos,"credito_ilustrativo_centavos":(x.pontos//100)*500}
