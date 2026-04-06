from sqlalchemy import Column, Integer, String, Text, Boolean
from app.database import Base


class Candidato(Base):
    __tablename__ = "candidatos"

    id                      = Column(Integer, primary_key=True, index=True)
    nombre                  = Column(String)
    nombre_archivo          = Column(String)
    hash_archivo            = Column(String, unique=True)

    texto_completo          = Column(Text)

    perfil                  = Column(Text)
    experiencia             = Column(Text)
    educacion               = Column(Text)
    habilidades             = Column(Text)
    formacion_complementaria = Column(Text)   # ← NUEVO

    embedding               = Column(Text)


class Usuario(Base):
    __tablename__ = "usuarios"

    id       = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    activo   = Column(Boolean, default=True)
    creado   = Column(String, default="")
