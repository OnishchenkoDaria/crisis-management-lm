from fastapi import FastAPI
import os
from typing import Optional
from app.users.router import router as user_router
from app.ingest.router import router as ingest_router
from app.rag.router import router as rag_router
from app.auth.router import router as auth_router
from app.analysis.router import router as analysis_router
from app.chats.router import router as chat_router

app = FastAPI()

@app.get("/")
def check_connection():
    return({
      "message": "Hello world!"
    })

app.include_router(auth_router)
app.include_router(user_router)
# each chat is associated with a workspace
app.include_router(chat_router)
app.include_router(ingest_router)
app.include_router(rag_router)
app.include_router(analysis_router)