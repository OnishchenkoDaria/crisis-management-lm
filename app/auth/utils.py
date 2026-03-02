from datetime import timedelta, datetime
from sys import exec_prefix

import jwt
from passlib.context import CryptContext

import os
from dotenv import load_dotenv

load_dotenv()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
def hash_password(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta if expires_delta else timedelta(
        minutes=int(os.getenv('ACCESS_TOKEN_EXPIRES_MINUTES'))
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, os.getenv('SECRET_KEY'), algorithm=os.getenv('ALGORITHM'))
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, os.getenv('SECRET_KEY'), algorithms=[os.getenv('ALGORITHM')])
        return payload
    except jwt.ExpiredSignatureError:
        print("Signature has expired")
    except jwt.InvalidTokenError:
        print("Signature has expired")