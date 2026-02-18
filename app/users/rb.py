class RBUser:
    def __init__(self,
                 user_id: int | None,
                 name: str | None,
                 email: str | None,):
        self.id = user_id
        self.name = name
        self.email = email

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "email": self.email
        }
        # creating dictionary copy to avoid changing the dictionary during iteration
        filtered_data =  {
            key: value for key, value in data.items() if value is not None
        }
        return filtered_data