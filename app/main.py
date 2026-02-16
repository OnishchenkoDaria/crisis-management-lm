from fastapi import FastAPI
import os
from typing import Optional
from app.users.router import router as user_router

app = FastAPI()

@app.get("/")
def check_connection():
    return({
      "message": "Hello world!"
    })

app.include_router(user_router)