from sqlalchemy import Column, Integer, String, Float
from database import Base

class Tovar(Base):
    __tablename__ = "sklad"

    id = Column(Integer, primary_key=True, index=True)
    nazov = Column(String, unique=True, index=True, nullable=False)
    cena = Column(Float, nullable=False)
    pocet = Column(Integer, nullable=False)