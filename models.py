from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, Float, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import enum

# Database setup - use SQLite locally, PostgreSQL in production
DATABASE_URL = os.getenv("DATABASE_URL")

# If no DATABASE_URL (local development), use SQLite
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./saas.db"
    print("Using SQLite locally")
else:
    print(f"Using PostgreSQL: {DATABASE_URL[:50]}...")

# Handle SQLite vs PostgreSQL
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============ ENUMS ============
class CampaignStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    DRAFT = "draft"

class EmailStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    BOUNCED = "bounced"
    OPENED = "opened"
    REPLIED = "replied"
    FAILED = "failed"

# ============ MODELS ============

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    company_name = Column(String)
    role = Column(String, default="admin")
    created_at = Column(DateTime, default=datetime.utcnow)

    campaigns = relationship("Campaign", back_populates="user")

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    name = Column(String, index=True)
    client_name = Column(String)
    description = Column(Text, nullable=True)
    status = Column(Enum(CampaignStatus), default=CampaignStatus.DRAFT)
    
    total_leads = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    replies_received = Column(Integer, default=0)
    opens = Column(Integer, default=0)
    
    subject_line = Column(String, nullable=True)
    email_template = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="campaigns")
    leads = relationship("Lead", back_populates="campaign", cascade="all, delete-orphan")
    email_logs = relationship("EmailLog", back_populates="campaign", cascade="all, delete-orphan")

class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True)
    campaign_id = Column(String, ForeignKey("campaigns.id"))
    
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, index=True)
    company = Column(String, nullable=True)
    title = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    
    status = Column(String, default="pending")
    imported_at = Column(DateTime, default=datetime.utcnow)
    
    campaign = relationship("Campaign", back_populates="leads")
    email_logs = relationship("EmailLog", back_populates="lead", cascade="all, delete-orphan")

class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(String, primary_key=True)
    campaign_id = Column(String, ForeignKey("campaigns.id"))
    lead_id = Column(String, ForeignKey("leads.id"))
    
    recipient_email = Column(String, index=True)
    subject = Column(String)
    body = Column(Text)
    
    status = Column(Enum(EmailStatus), default=EmailStatus.PENDING)
    sent_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    
    open_count = Column(Integer, default=0)
    click_count = Column(Integer, default=0)
    
    resend_email_id = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="email_logs")
    lead = relationship("Lead", back_populates="email_logs")

class Reply(Base):
    __tablename__ = "replies"

    id = Column(String, primary_key=True)
    email_log_id = Column(String, ForeignKey("email_logs.id"))
    
    from_email = Column(String)
    to_email = Column(String)
    subject = Column(String)
    body = Column(Text)
    
    received_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(String, primary_key=True)
    email_log_id = Column(String, ForeignKey("email_logs.id"), nullable=True)
    event_type = Column(String)
    data = Column(Text)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# ============ CREATE TABLES ============
def init_db():
    Base.metadata.create_all(bind=engine)

# ============ DATABASE SESSION ============
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()