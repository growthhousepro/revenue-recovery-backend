from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import uuid
import os
from models import Campaign, Lead, EmailLog, CampaignStatus, EmailStatus, get_db, User
from jose import jwt, JWTError

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

# ============ HELPER ============
def get_current_user_id(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============ SCHEMAS ============
class LeadCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    company: str = None
    title: str = None
    phone: str = None

class CampaignCreate(BaseModel):
    name: str
    client_name: str
    description: str = None
    subject_line: str
    email_template: str

class CampaignUpdate(BaseModel):
    name: str = None
    client_name: str = None
    description: str = None
    subject_line: str = None
    email_template: str = None

class CampaignResponse(BaseModel):
    id: str
    name: str
    client_name: str
    status: str
    total_leads: int
    emails_sent: int
    replies_received: int
    opens: int
    created_at: datetime

class DetailedCampaignResponse(CampaignResponse):
    description: str
    subject_line: str
    email_template: str
    started_at: datetime = None
    completed_at: datetime = None

# ============ ENDPOINTS ============

@router.post("/", response_model=DetailedCampaignResponse)
def create_campaign(
    campaign: CampaignCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaign_id = str(uuid.uuid4())
    
    db_campaign = Campaign(
        id=campaign_id,
        user_id=user_id,
        name=campaign.name,
        client_name=campaign.client_name,
        description=campaign.description,
        subject_line=campaign.subject_line,
        email_template=campaign.email_template,
        status=CampaignStatus.DRAFT
    )
    
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    
    return {
        "id": db_campaign.id,
        "name": db_campaign.name,
        "client_name": db_campaign.client_name,
        "status": db_campaign.status.value,
        "total_leads": db_campaign.total_leads,
        "emails_sent": db_campaign.emails_sent,
        "replies_received": db_campaign.replies_received,
        "opens": db_campaign.opens,
        "created_at": db_campaign.created_at,
        "description": db_campaign.description,
        "subject_line": db_campaign.subject_line,
        "email_template": db_campaign.email_template
    }

@router.get("/", response_model=list)
def list_campaigns(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaigns = db.query(Campaign).filter(Campaign.user_id == user_id).all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "client_name": c.client_name,
            "status": c.status.value,
            "total_leads": c.total_leads,
            "emails_sent": c.emails_sent,
            "replies_received": c.replies_received,
            "opens": c.opens,
            "created_at": c.created_at
        }
        for c in campaigns
    ]

@router.get("/{campaign_id}", response_model=DetailedCampaignResponse)
def get_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    return {
        "id": campaign.id,
        "name": campaign.name,
        "client_name": campaign.client_name,
        "status": campaign.status.value,
        "total_leads": campaign.total_leads,
        "emails_sent": campaign.emails_sent,
        "replies_received": campaign.replies_received,
        "opens": campaign.opens,
        "created_at": campaign.created_at,
        "description": campaign.description,
        "subject_line": campaign.subject_line,
        "email_template": campaign.email_template,
        "started_at": campaign.started_at,
        "completed_at": campaign.completed_at
    }

@router.put("/{campaign_id}", response_model=DetailedCampaignResponse)
def update_campaign(
    campaign_id: str,
    campaign_update: CampaignUpdate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    if campaign_update.name:
        campaign.name = campaign_update.name
    if campaign_update.client_name:
        campaign.client_name = campaign_update.client_name
    if campaign_update.description:
        campaign.description = campaign_update.description
    if campaign_update.subject_line:
        campaign.subject_line = campaign_update.subject_line
    if campaign_update.email_template:
        campaign.email_template = campaign_update.email_template
    
    campaign.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(campaign)
    
    return {
        "id": campaign.id,
        "name": campaign.name,
        "client_name": campaign.client_name,
        "status": campaign.status.value,
        "total_leads": campaign.total_leads,
        "emails_sent": campaign.emails_sent,
        "replies_received": campaign.replies_received,
        "opens": campaign.opens,
        "created_at": campaign.created_at,
        "description": campaign.description,
        "subject_line": campaign.subject_line,
        "email_template": campaign.email_template
    }

@router.delete("/{campaign_id}")
def delete_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    db.delete(campaign)
    db.commit()
    
    return {"message": "Campaign deleted"}

@router.post("/{campaign_id}/add-leads")
def add_leads(
    campaign_id: str,
    leads: list[LeadCreate],
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    added_leads = []
    for lead_data in leads:
        lead_id = str(uuid.uuid4())
        db_lead = Lead(
            id=lead_id,
            campaign_id=campaign_id,
            first_name=lead_data.first_name,
            last_name=lead_data.last_name,
            email=lead_data.email,
            company=lead_data.company,
            title=lead_data.title,
            phone=lead_data.phone
        )
        db.add(db_lead)
        added_leads.append(db_lead)
    
    campaign.total_leads += len(leads)
    db.commit()
    
    return {
        "message": f"Added {len(leads)} leads",
        "total_leads": campaign.total_leads
    }

@router.post("/{campaign_id}/launch")
def launch_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    if campaign.status != CampaignStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Campaign must be in DRAFT status")
    
    if campaign.total_leads == 0:
        raise HTTPException(status_code=400, detail="Campaign must have leads")
    
    campaign.status = CampaignStatus.ACTIVE
    campaign.started_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": "Campaign launched",
        "status": campaign.status.value,
        "started_at": campaign.started_at
    }

@router.post("/{campaign_id}/send-emails")
def send_campaign_emails(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    from services.email_service import send_campaign_emails as send_emails
    
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    if campaign.total_leads == 0:
        raise HTTPException(status_code=400, detail="Campaign has no leads")
    
    result = send_emails(campaign_id, db)
    
    return result

@router.post("/{campaign_id}/pause")
def pause_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    campaign.status = CampaignStatus.PAUSED
    db.commit()
    
    return {"message": "Campaign paused", "status": campaign.status.value}

@router.post("/{campaign_id}/resume")
def resume_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    campaign.status = CampaignStatus.ACTIVE
    db.commit()
    
    return {"message": "Campaign resumed", "status": campaign.status.value}

@router.get("/{campaign_id}/analytics")
def get_campaign_analytics(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    email_logs = db.query(EmailLog).filter(EmailLog.campaign_id == campaign_id).all()
    
    total_sent = len([e for e in email_logs if e.status in [EmailStatus.SENT, EmailStatus.OPENED, EmailStatus.REPLIED]])
    total_opened = len([e for e in email_logs if e.status in [EmailStatus.OPENED, EmailStatus.REPLIED]])
    total_replied = len([e for e in email_logs if e.status == EmailStatus.REPLIED])
    
    open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
    reply_rate = (total_replied / total_sent * 100) if total_sent > 0 else 0
    
    return {
        "campaign_id": campaign_id,
        "total_leads": campaign.total_leads,
        "emails_sent": total_sent,
        "opens": total_opened,
        "replies": total_replied,
        "open_rate": round(open_rate, 2),
        "reply_rate": round(reply_rate, 2)
    }