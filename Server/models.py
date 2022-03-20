from sqlalchemy import Column, Integer, String, Enum, DateTime
from database import Base

class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    username = Column(String(200), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    password = Column(String(120), nullable=False)
    name = Column(String(200), nullable=False)
    login_id = Column(String(36), nullable=True)
    currentGameId = Column(String(36), nullable=True)
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    def get_id(self):
        return self.login_id

    def is_confirmed(self):
        return self.confirmed

class Device(Base):
    __tablename__ = 'device'
    id = Column(Integer, primary_key=True)
    deviceId = Column(String(12), unique=True, nullable=False)
    status = Column(Enum("disconnected", "connected", "unregistrated", "inGame"), default='unregistrated')
    lastOnline = Column(DateTime, nullable=True)