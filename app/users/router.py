from fastapi import APIRouter, Depends
from app.users.dao import UserDAO
from app.users.rb import RBUser
from app.users.schemas import SchemaUser

router = APIRouter(
    prefix="/users",
    tags=["Processing users' data"],
)

@router.get("/", summary="Get all users")
async def get_users(request_body: RBUser = Depends()) -> list[SchemaUser]:
    return await UserDAO.find_all(**request_body.to_dict())