from datetime import timedelta, datetime, timezone
from sys import exec_prefix
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

import jwt
from passlib.context import CryptContext

import os
from dotenv import load_dotenv

load_dotenv()

ALLOWED_ALGS = {"HS256", "RS256", "EdDSA"}
if ALGORITHM not in ALLOWED_ALGS:
    raise ValueError(f"Unsupported JWT alg: {ALGORITHM}")

ISSUER = os.getenv("JWT_ISSUER", "crisis-management-api")
AUDIENCE = os.getenv("JWT_AUDIENCE", "crisis-management-client")

PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")   # for RS256/EdDSA verify
PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY") # for RS256/EdDSA sign

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
def hash_password(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    to_encode = data.copy()
    to_encode.update({
        "iat": now,
        "exp": expire,
        "iss": ISSUER,
        "aud": AUDIENCE,
    })

    if ALGORITHM == "HS256":
        if not SECRET_KEY or len(SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be set and strong (>=32 chars recommended).")
        key = SECRET_KEY
    else:
        if not PRIVATE_KEY:
            raise ValueError("JWT_PRIVATE_KEY must be set for RS256/EdDSA.")
        key = PRIVATE_KEY

    return jwt.encode(to_encode, key, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    if ALGORITHM == "HS256":
        key = SECRET_KEY
    else:
        key = PUBLIC_KEY

    if not key:
        raise ValueError("Missing key for token ver")
    return jwt.decode(
        token,
        key,
        algorithms=[ALGORITHM],
        audience=AUDIENCE,
        issuer=ISSUER,
        options={
            "require": ["exp", "iat", "iss", "aud"]
        }
    )