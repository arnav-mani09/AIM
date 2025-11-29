from typing import Any

from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    id: Any

    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore
        return cls.__name__.lower()
