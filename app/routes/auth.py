from fastapi import APIRouter,Depends,HTTPException
from app.schemas.models import Register,Login
from app.database import db
from app.security.passwords import hash_password,verify_password
from app.security.auth import token,current
router=APIRouter(prefix="/auth",tags=["Autenticação"])
@router.post("/usuarios",status_code=201)
def register(x:Register):
    with db() as c:
        try: cur=c.execute("INSERT INTO users(name,email,password,loyalty) VALUES(?,?,?,?)",(x.nome,x.email.lower(),hash_password(x.senha),int(x.consentimento_fidelidade)))
        except Exception: raise HTTPException(409,"E-mail já cadastrado")
    return {"id":cur.lastrowid,"perfil":"CLIENTE"}
@router.post("/login")
def login(x:Login):
    with db() as c: u=c.execute("SELECT * FROM users WHERE email=?",(x.email.lower(),)).fetchone()
    if not u or not verify_password(x.senha,u["password"]): raise HTTPException(401,"Credenciais inválidas")
    return {"token":token(u["id"],u["role"]),"tipo":"Bearer","perfil":u["role"]}
@router.get("/me")
def me(u=Depends(current)):
    return {"id":u["id"],"nome":u["name"],"email":u["email"],"perfil":u["role"]}
