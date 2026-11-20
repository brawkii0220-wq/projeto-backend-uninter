import hashlib,secrets,hmac
def hash_password(p):
    s=secrets.token_hex(16)
    return s+"$"+hashlib.pbkdf2_hmac("sha256",p.encode(),s.encode(),180000).hex()
def verify_password(p,v):
    try:
        s,h=v.split("$")
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256",p.encode(),s.encode(),180000).hex(),h)
    except ValueError: return False
