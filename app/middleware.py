import uuid,re
from starlette.middleware.base import BaseHTTPMiddleware
VALID=re.compile(r"^[A-Za-z0-9._:-]{8,100}$")
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        rid=request.headers.get("X-Request-ID","")
        if not VALID.fullmatch(rid): rid=str(uuid.uuid4())
        response=await call_next(request)
        response.headers["X-Request-ID"]=rid
        return response
