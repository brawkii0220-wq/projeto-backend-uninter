import uuid
from app.config import __dict__ as _unused
class MockGateway:
    """Provedor fictício. Nenhuma cobrança ou transferência financeira é realizada."""
    def request(self,order_id,amount,method):
        pid=str(uuid.uuid4())
        request={"order_id":order_id,"amount_centavos":amount,"currency":"BRL","method":method}
        response={"provider_reference":"MOCK-"+pid[:8].upper(),"status":"pending","test_mode":True,
                  "message":"Solicitação simulada recebida"}
        return pid,request,response
