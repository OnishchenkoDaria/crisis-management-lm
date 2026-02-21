from fastapi import APIRouter, Depends
from app.users.dao import UserDAO
from app.users.rb import RBUser
from app.users.schemas import SchemaUser, SchemaUserAdd, SchemaUserNameUpd, SchemaUserPasswordUpd

router = APIRouter(
    prefix="/users",
    tags=["Processing users' data"],
)

@router.get("/", summary="Get all users")
async def get_users(request_body: RBUser = Depends()) -> list[SchemaUser]:
    return await UserDAO.find_all(**request_body.to_dict())


@router.get("/{id}", summary="Get user by id")
async def get_user_by_id(user_id: int) -> SchemaUser | dict:
    result = await UserDAO.find_one_or_none_by_id(user_id)
    if result is None:
        return {'message': f'No user with id = {user_id} is found'}
    return result

@router.post("/add/")
async def register_user(data: SchemaUserAdd) -> dict:
    check = await UserDAO.add(**data.dict())
    if check:
        return {"message": "User added", "login data": data}
    else:
        return {"message": "Error creating user", "login data": data}

@router.put("/update_description/")
async def update_major_description(major: SMajorsUpdDesc) -> dict:
    check = await MajorsDAO.update(filter_by={'major_name': major.major_name},
                                   major_description=major.major_description)
    if check:
        return {"message": "Описание факультета успешно обновлено!", "major": major}
    else:
        return {"message": "Ошибка при обновлении описания факультета!"}


@router.put("/update_name/")
async def update_major_description(data: SchemaUserNameUpd) -> dict:
    check = await UserDAO.update(filter_by={'email': data.email},
                                   username=data.name)
    if check:
        return {"message": "Username updated!", "name": data.name}
    else:
        return {"message": "Error updating user's name"}

@router.put("/update_password/")
async def update_major_description(data: SchemaUserPasswordUpd) -> dict:
    check = await UserDAO.update(filter_by={'email': data.email},
                                   password=data.password)
    if check:
        return {"message": "User's password updated!", "password": data.password}
    else:
        return {"message": "Error updating user's password"}

@router.delete("/delete/{major_id}")
async def delete_major(user_id: int) -> dict:
    check = await UserDAO.delete(id=user_id)
    if check:
        return {"message": f"User with ID {user_id} deleted!"}
    else:
        return {"message": f"Error deleting usr with ID={user_id}"}
