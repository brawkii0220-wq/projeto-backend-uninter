from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.middleware import RequestIDMiddleware
from app.routes import auth,catalog,orders,stock,loyalty,campaigns,payments
app=FastAPI(title="Raízes do Nordeste API",version="1.0.0",docs_url="/api/docs",openapi_url="/api/openapi.json")
app.add_middleware(RequestIDMiddleware)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000","http://localhost:5173"],allow_methods=["*"],allow_headers=["*"])
@app.on_event("startup")
def startup(): init_db()
@app.get("/api/health")
def health(): return {"status":"online","projeto":"Raízes do Nordeste"}
for r in [auth.router,catalog.router,orders.router,stock.router,loyalty.router,campaigns.router,payments.router]:
    app.include_router(r,prefix="/api")
