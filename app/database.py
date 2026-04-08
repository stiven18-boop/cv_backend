import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Usa la variable de entorno en Render, SQLite en local
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./cv_database.db"
)

# Render entrega URLs con "postgres://", SQLAlchemy necesita "postgresql://"
if DATABASE_URL.startswith("postgresql://bolsa_empleo_db_user:ziTbOhYrTujbQMB8Tr36edr56q3IS831@dpg-d79t5lidbo4c73airqpg-a/bolsa_empleo_db"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://bolsa_empleo_db_user:ziTbOhYrTujbQMB8Tr36edr56q3IS831@dpg-d79t5lidbo4c73airqpg-a/bolsa_empleo_db", "postgresql://bolsa_empleo_db_user:ziTbOhYrTujbQMB8Tr36edr56q3IS831@dpg-d79t5lidbo4c73airqpg-a/bolsa_empleo_db", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()