from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, Enum
from app.database import Base, str_uniq, int_pk, str_not_null

class User(Base):
    id: Mapped[int_pk]
    name: Mapped[str_not_null]
    email: Mapped[str_uniq]
    role: Mapped[str] = mapped_column(
        Enum('admin', 'user', name='user_role_enum', create_type=False),
        nullable=False
    )
    hashed_password: Mapped[str_not_null]

    # present objects as string data
    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"user_name={self.name!r},"
                f"user_email={self.email!r})")

    def __repr__(self):
        return str(self)

    #transform received data into dictionary
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
        }