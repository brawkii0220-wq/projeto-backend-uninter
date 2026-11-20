import sqlite3
from contextlib import contextmanager
from app.config import DATABASE

@contextmanager
def db():
    c=sqlite3.connect(DATABASE, timeout=20)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,password TEXT,role TEXT DEFAULT 'CLIENTE',points INTEGER DEFAULT 0,loyalty INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS units(id INTEGER PRIMARY KEY,name TEXT,address TEXT,active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,unit_id INTEGER,name TEXT,description TEXT,price INTEGER,active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS stock(product_id INTEGER PRIMARY KEY,quantity INTEGER NOT NULL CHECK(quantity>=0));
        CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,product_id INTEGER,kind TEXT,quantity INTEGER,before_qty INTEGER,after_qty INTEGER,reason TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,user_id INTEGER,unit_id INTEGER,channel TEXT,status TEXT,subtotal INTEGER,discount INTEGER,total INTEGER,created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY,order_id TEXT,product_id INTEGER,name TEXT,quantity INTEGER,unit_price INTEGER,line_total INTEGER);
        CREATE TABLE IF NOT EXISTS campaigns(id INTEGER PRIMARY KEY,code TEXT UNIQUE,description TEXT,percent INTEGER,min_total INTEGER,active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY,order_id TEXT,status TEXT,amount INTEGER,request TEXT,response TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS loyalty_events(id INTEGER PRIMARY KEY,user_id INTEGER,points INTEGER,description TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            from app.security.passwords import hash_password
            c.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",("Admin","admin@raizes.com",hash_password("admin123"),"ADMIN"))
        if not c.execute("SELECT 1 FROM units LIMIT 1").fetchone():
            c.execute("INSERT INTO units(name,address) VALUES('Centro','Endereço demonstrativo')")
            uid=c.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            for n,d,p,q in [("Tapioca","Tradicional",1500,30),("Cuscuz","Nordestino",1800,25),("Suco de Cajá","Natural",900,20),("Carne de Sol","Prato regional",3200,12)]:
                cur=c.execute("INSERT INTO products(unit_id,name,description,price) VALUES(?,?,?,?)",(uid,n,d,p))
                c.execute("INSERT INTO stock VALUES(?,?)",(cur.lastrowid,q))
                c.execute("INSERT INTO movements(product_id,kind,quantity,before_qty,after_qty,reason) VALUES(?,'ENTRADA',?,0,?,'Carga inicial')",(cur.lastrowid,q,q))
            c.execute("INSERT INTO campaigns(code,description,percent,min_total) VALUES('NORDESTE10','Desconto de 10%',10,3000)")
