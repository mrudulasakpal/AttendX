from sqlalchemy import Column, Integer, String, Enum as SQLAlchemyEnum
from database import Base
import enum

class Role(str, enum.Enum):
    student = "student"
    teacher = "teacher"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True) # Roll number for students
    password = Column(String)
    role = Column(String) # We'll store it as a simple string for simplicity
