import os

from sqlalchemy import Boolean, Column, DateTime, Integer, String, create_engine, JSON, Text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://backup:backup@localhost:5432/inventory",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class CredentialProfile(Base):
    __tablename__ = "credential_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    group_name = Column(String(64), nullable=False, index=True)
    username = Column(String(128), nullable=False, default="admin")
    password = Column(String(256), nullable=False, default="changeme")


class Network(Base):
    __tablename__ = "networks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    network = Column(String(64), nullable=False, index=True)
    group_name = Column(String(64), nullable=False, default="default", index=True)
    environment_name = Column(String(128), nullable=True)
    gateway = Column(String(64), nullable=True)


class DeviceRecord(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    ip = Column(String(64), nullable=False)
    model = Column(String(64), nullable=False, default="routeros")
    group = Column(String(64), nullable=False, default="default")
    enabled = Column(Boolean, nullable=False, default=True)
    ports = Column(JSON, nullable=False, default=list)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(32), nullable=False, default="viewer")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=True)


def get_session():
    return SessionLocal()
