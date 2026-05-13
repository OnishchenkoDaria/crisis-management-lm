from fastapi import FastAPI
import os
from typing import Optional
from app.users.router import router as user_router
from app.ingest.router import router as ingest_router
from app.rag.router import router as rag_router

app = FastAPI()

@app.get("/")
def check_connection():
    return({
      "message": "Hello world!"
    })

app.include_router(user_router)
app.include_router(ingest_router)
app.include_router(rag_router)