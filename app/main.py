from fastapi import FastAPI
import os
from typing import Optional

app = FastAPI()

@app.get("/")
def check_connection():
    return({
      "message": "Hello world!"
    })