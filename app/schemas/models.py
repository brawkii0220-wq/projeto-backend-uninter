from pydantic import BaseModel,EmailStr,Field
class Register(BaseModel):
    nome:str
    email:EmailStr
    senha:str=Field(min_length=8)
    consentimento_fidelidade:bool=False
class Login(BaseModel):
    email:EmailStr
    senha:str
class Unit(BaseModel):
    nome:str
    endereco:str=""
class Product(BaseModel):
    unidade_id:int
    nome:str
    descricao:str=""
    preco_centavos:int=Field(ge=0)
    estoque:int=Field(ge=0)
class Item(BaseModel):
    produto_id:int
    quantidade:int=Field(gt=0,le=50)
class Order(BaseModel):
    unidade_id:int
    canal:str="APP"
    itens:list[Item]=Field(min_length=1)
    cupom:str|None=None
class Status(BaseModel):
    status:str
class Movement(BaseModel):
    tipo:str
    quantidade:int=Field(gt=0)
    motivo:str=""
class Campaign(BaseModel):
    codigo:str
    descricao:str
    percentual:int=Field(ge=1,le=100)
    minimo_centavos:int=0
class Payment(BaseModel):
    forma_pagamento:str
class Redeem(BaseModel):
    pontos:int=Field(gt=0)
