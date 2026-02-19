from datetime import datetime, date
from typing import Optional
import re
from pydantic import BaseModel, Field, EmailStr, validator

class SchemaUser(BaseModel):
    id: int
    name: str = Field(..., min_length=1, max_length=50, description="User name 1-50 symbols")
    email: EmailStr = Field(..., description="User's email")
    hashed_password: str = Field(..., description="User's hashed password")

class SchemaUSerAdd(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="User name 1-50 symbols")
    email: EmailStr = Field(..., description="User's email")
    password: str = Field(..., min_length=1, max_length=8, description="User's password")