from sqlalchemy import create_engine, Column, String, Integer, DateTime, Float, Boolean, ForeignKey, Enum, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import uuid
from enum import Enum as PyEnum
import os

DATABASE_URL = "sqlite:///./saas.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===== ENUMS =====

class UserRole(str, PyEnum):
    CLIENT = "client"
    ADMIN = "admin"

class TeamRole(str, PyEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

class CampaignStatus(str, PyEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"

class EmailStatus(str, PyEnum):
    SENT = "sent"
    OPENED = "opened"
    REPLIED = "replied"
    BOUNCED = "bounced"
    FAILED = "failed"

class BookingStatus(str, PyEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELED = "canceled"

class NotificationType(str, PyEnum):
    EMAIL_REPLY = "email_reply"
    BOOKING_CONFIRMED = "booking_confirmed"
    CAMPAIGN_LAUNCHED = "campaign_launched"
    CAMPAIGN_COMPLETED = "campaign_completed"

class Plan(str, PyEnum):
    LAUNCH = "launch"
    SCALE = "scale"

class SubscriptionStatus(str, PyEnum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    PAUSED = "paused"

# ===== USERS & TEAMS =====

class Team(Base):
    __tablename__ = "teams"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    sender_email = Column(String)
    team_id = Column(String, ForeignKey('teams.id'))
    role = Column(String, default=UserRole.CLIENT)
    notify_on_reply = Column(Boolean, default=True)
    notify_on_booking = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class TeamMember(Base):
    __tablename__ = "team_members"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    role = Column(String, default=TeamRole.MEMBER)
    created_at = Column(DateTime, default=datetime.utcnow)

class TeamInvite(Base):
    __tablename__ = "team_invites"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, default=TeamRole.MEMBER)
    created_at = Column(DateTime, default=datetime.utcnow)

# ===== CAMPAIGNS & LEADS =====

class Campaign(Base):
    __tablename__ = "campaigns"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    name = Column(String, nullable=False)
    client_name = Column(String)
    description = Column(String)
    subject_line = Column(String, nullable=False)
    email_template = Column(Text, nullable=False)
    status = Column(String, default=CampaignStatus.DRAFT)
    total_leads = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    replies_received = Column(Integer, default=0)
    bookings_confirmed = Column(Integer, default=0)
    opens = Column(Integer, default=0)
    charge_booking_fee = Column(Boolean, default=True)
    follow_up_1_enabled = Column(Boolean, default=False)
    follow_up_1_days = Column(Integer, default=3)
    follow_up_1_template_id = Column(String)
    follow_up_2_enabled = Column(Boolean, default=False)
    follow_up_2_days = Column(Integer, default=7)
    follow_up_2_template_id = Column(String)
    follow_up_3_enabled = Column(Boolean, default=False)
    follow_up_3_days = Column(Integer, default=30)
    follow_up_3_template_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Lead(Base):
    __tablename__ = "leads"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String, ForeignKey('campaigns.id'), nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, nullable=False)
    company = Column(String)
    title = Column(String)
    phone = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# ===== EMAILS & TEMPLATES =====

class EmailLog(Base):
    __tablename__ = "email_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String, ForeignKey('campaigns.id'), nullable=False)
    lead_id = Column(String, ForeignKey('leads.id'), nullable=False)
    recipient_email = Column(String, nullable=False)
    subject = Column(String)
    body = Column(Text)
    status = Column(String, default=EmailStatus.SENT)
    resend_email_id = Column(String)
    is_follow_up = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    opened_at = Column(DateTime)
    replied_at = Column(DateTime)
    reply_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class EmailTemplate(Base):
    __tablename__ = "email_templates"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    campaign_type = Column(String)
    call_to_action = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# ===== BOOKINGS =====

class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String, ForeignKey('campaigns.id'), nullable=False)
    lead_id = Column(String, ForeignKey('leads.id'), nullable=False)
    email_log_id = Column(String, ForeignKey('email_logs.id'))
    appointment_date = Column(DateTime)
    client_name = Column(String)
    status = Column(String, default=BookingStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)

# ===== NOTIFICATIONS =====

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    type = Column(String)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    related_campaign_id = Column(String, ForeignKey('campaigns.id'))
    related_booking_id = Column(String, ForeignKey('bookings.id'))
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# ===== FOLLOW-UPS =====

class FollowUpEmail(Base):
    __tablename__ = "follow_up_emails"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String, ForeignKey('campaigns.id'), nullable=False)
    original_email_log_id = Column(String, ForeignKey('email_logs.id'), nullable=False)
    lead_id = Column(String, ForeignKey('leads.id'), nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

# ===== BILLING =====

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    plan = Column(String, nullable=False)
    status = Column(String, default=SubscriptionStatus.ACTIVE)
    stripe_customer_id = Column(String, unique=True, nullable=False)
    stripe_subscription_id = Column(String, unique=True)
    stripe_price_id = Column(String)
    current_period_start = Column(DateTime, default=datetime.utcnow)
    current_period_end = Column(DateTime)
    canceled_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UsageRecord(Base):
    __tablename__ = "usage_records"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    usage_type = Column(String, nullable=False)
    quantity = Column(Integer, default=1)
    cost = Column(Float)
    campaign_id = Column(String, ForeignKey('campaigns.id'))
    meta_data = Column(String)
    billing_period_start = Column(DateTime)
    billing_period_end = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    stripe_invoice_id = Column(String, unique=True)
    stripe_payment_intent_id = Column(String)
    amount = Column(Float)
    currency = Column(String, default="usd")
    status = Column(String)
    invoice_url = Column(String)
    description = Column(String)
    billing_reason = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ===== DATABASE INITIALIZATION =====

def init_db():
    Base.metadata.create_all(bind=engine)