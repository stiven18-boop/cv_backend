from sqlalchemy import Column, Integer, String, Text
from app.database import Base


class Candidato(Base):
    __tablename__ = "candidatos"

    id = Column(Integer, primary_key=True, index=True)

    nombre = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=True)
    telefono = Column(String(50), nullable=True)

    habilidades = Column(Text, nullable=True)
    experiencia = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Candidato(nombre={self.nombre}, email={self.email})>"
