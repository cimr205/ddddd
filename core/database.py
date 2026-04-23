import os
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    company = Column(String(255), index=True)
    email = Column(String(255), index=True)
    phone = Column(String(64))
    website = Column(String(512))
    address = Column(String(512))
    niche = Column(String(128))
    source = Column(String(64))
    email_confidence = Column(Float, default=0.0)
    status = Column(String(32), default="new")
    created_at = Column(DateTime, default=datetime.utcnow)
    emails = relationship("EmailLog", back_populates="lead")


class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    niche = Column(String(128))
    status = Column(String(32), default="idle")
    subject_template = Column(Text)
    body_template = Column(Text)
    leads_total = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    emails = relationship("EmailLog", back_populates="campaign")


class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    subject = Column(Text)
    body = Column(Text)
    status = Column(String(32), default="pending")
    error = Column(Text)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    lead = relationship("Lead", back_populates="emails")
    campaign = relationship("Campaign", back_populates="emails")


class AgentEvent(Base):
    __tablename__ = "agent_events"
    id = Column(Integer, primary_key=True, index=True)
    agent = Column(String(64), index=True)
    action = Column(String(255))
    detail = Column(Text)
    status = Column(String(32))
    score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatHistory(Base):
    __tablename__ = "chat_history"
    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(16))       # user | agent | system
    content = Column(Text)
    msg_type = Column(String(32), default="text")  # text | result | error
    created_at = Column(DateTime, default=datetime.utcnow)


async def init_db():
    os.makedirs("data", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
