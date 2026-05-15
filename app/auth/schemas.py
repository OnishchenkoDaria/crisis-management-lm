from pydantic import BaseModel, EmailStr, Field


class SchemaLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class SchemaTokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SchemaRefreshRequest(BaseModel):
    refresh_token: str