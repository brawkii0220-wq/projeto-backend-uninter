import time,json,base64,hmac,hashlib
from fastapi import Header,HTTPException,Depends
from app.config import JWT_SECRET
from app.database import db
def b64(x): return base64.urlsafe_b64encode(x).rstrip(b"=").decode()
def token(uid,role):
    h=b64(b'{"alg":"HS256","typ":"JWT"}')
    p=b64(json.dumps({"sub":uid,"role":role,"exp":int(time.time())+3600}).encode())
    body=h+"."+p
    return body+"."+b64(hmac.new(JWT_SECRET.encode(),body.encode(),hashlib.sha256).digest())
def current(authorization:str=Header(default="")):
    try:
        t=authorization.removeprefix("Bearer ")
        h,p,s=t.split("."); body=h+"."+p
        sig=b64(hmac.new(JWT_SECRET.encode(),body.encode(),hashlib.sha256).digest())
        if not hmac.compare_digest(sig,s): raise ValueError()
        data=json.loads(base64.urlsafe_b64decode(p+"="*(-len(p)%4)))
        if data["exp"]<time.time(): raise ValueError()
        with db() as c: u=c.execute("SELECT * FROM users WHERE id=?",(data["sub"],)).fetchone()
        if not u: raise ValueError()
        return dict(u)
    except Exception: raise HTTPException(401,"Token inválido ou expirado")
def roles(*allowed):
    def check(u=Depends(current)):
        if u["role"] not in allowed: raise HTTPException(403,"Acesso negado")
        return u
    return check
