from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from jose import jwt, JWTError
import uuid
import os
import csv
import io
import requests

from models import (
    Campaign, CampaignStatus, Lead, EmailLog, EmailStatus, 
    User, get_db
)

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@example.com")

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

class CreateCampaignRequest(BaseModel):
    name: str
    client_name: str
    subject_line: str
    email_template: str
    description: str = ""

class UpdateCampaignRequest(BaseModel):
    name: str = None
    client_name: str = None
    subject_line: str = None
    email_template: str = None
    description: str = None

@router.post("/")
def create_campaign(
    request: CreateCampaignRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Create a new campaign"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.team_id:
        raise HTTPException(status_code=400, detail="User is not part of a team")
    
    campaign_id = str(uuid.uuid4())
    
    new_campaign = Campaign(
        id=campaign_id,
        team_id=user.team_id,
        user_id=user_id,
        name=request.name,
        client_name=request.client_name,
        subject_line=request.subject_line,
        email_template=request.email_template,
        description=request.description,
        status=CampaignStatus.DRAFT
    )
    
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)
    
    return {
        "id": new_campaign.id,
        "name": new_campaign.name,
        "status": new_campaign.status,
        "created_at": new_campaign.created_at
    }

@router.get("/")
def list_campaigns(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """List all campaigns for user"""
    campaigns = db.query(Campaign).filter(Campaign.user_id == user_id).all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "client_name": c.client_name,
            "status": c.status,
            "total_leads": c.total_leads,
            "emails_sent": c.emails_sent,
            "replies_received": c.replies_received,
            "bookings_confirmed": c.bookings_confirmed,
            "opens": c.opens,
            "charge_booking_fee": c.charge_booking_fee,
            "created_at": c.created_at
        }
        for c in campaigns
    ]

@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get a specific campaign"""
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
        "description": campaign.description,
        "subject_line": campaign.subject_line,
        "email_template": campaign.email_template,
        "status": campaign.status,
        "total_leads": campaign.total_leads,
        "emails_sent": campaign.emails_sent,
        "replies_received": campaign.replies_received,
        "bookings_confirmed": campaign.bookings_confirmed,
        "opens": campaign.opens,
        "charge_booking_fee": campaign.charge_booking_fee,
        "follow_up_1_enabled": campaign.follow_up_1_enabled,
        "follow_up_1_days": campaign.follow_up_1_days,
        "follow_up_1_template_id": campaign.follow_up_1_template_id,
        "follow_up_2_enabled": campaign.follow_up_2_enabled,
        "follow_up_2_days": campaign.follow_up_2_days,
        "follow_up_2_template_id": campaign.follow_up_2_template_id,
        "follow_up_3_enabled": campaign.follow_up_3_enabled,
        "follow_up_3_days": campaign.follow_up_3_days,
        "follow_up_3_template_id": campaign.follow_up_3_template_id,
        "created_at": campaign.created_at
    }

@router.put("/{campaign_id}")
def update_campaign(
    campaign_id: str,
    request: UpdateCampaignRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Update a campaign"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    if request.name:
        campaign.name = request.name
    if request.client_name:
        campaign.client_name = request.client_name
    if request.subject_line:
        campaign.subject_line = request.subject_line
    if request.email_template:
        campaign.email_template = request.email_template
    if request.description is not None:
        campaign.description = request.description
    
    db.commit()
    
    return {"message": "Campaign updated"}

@router.delete("/{campaign_id}")
def delete_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Delete a campaign"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    db.delete(campaign)
    db.commit()
    
    return {"message": "Campaign deleted"}

@router.post("/{campaign_id}/import-leads-csv")
def import_leads_csv(
    campaign_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Import leads from CSV"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    try:
        contents = file.file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(contents))
        
        if not csv_reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV file is empty")
        
        if 'email' not in csv_reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV must have 'email' column")
        
        added = 0
        for row in csv_reader:
            if not row.get('email'):
                continue
            
            email = row.get('email', '').strip()
            first_name = row.get('first_name', '').strip()
            last_name = row.get('last_name', '').strip()
            company = row.get('company', '').strip() if 'company' in row else None
            
            if not first_name and not last_name:
                if company:
                    first_name = company
                    last_name = "Contact"
                else:
                    first_name = "Lead"
                    last_name = "Import"
            
            lead = Lead(
                id=str(uuid.uuid4()),
                campaign_id=campaign_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                company=company,
                title=row.get('title', '').strip() if 'title' in row else None,
                phone=row.get('phone', '').strip() if 'phone' in row else None,
            )
            db.add(lead)
            added += 1
        
        campaign.total_leads += added
        db.commit()
        
        return {
            "added": added,
            "message": f"Successfully imported {added} leads"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing CSV: {str(e)}")

@router.post("/{campaign_id}/launch")
def launch_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Launch a campaign"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    campaign.status = CampaignStatus.ACTIVE
    db.commit()
    
    return {"message": "Campaign launched", "status": campaign.status}

@router.post("/{campaign_id}/send-emails")
def send_emails(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Send emails for a campaign"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    leads = db.query(Lead).filter(Lead.campaign_id == campaign_id).all()
    
    sent = 0
    for lead in leads:
        existing_email = db.query(EmailLog).filter(
            EmailLog.campaign_id == campaign_id,
            EmailLog.lead_id == lead.id
        ).first()
        
        if existing_email:
            continue
        
        user = db.query(User).filter(User.id == user_id).first()
        from_addr = user.sender_email if user.sender_email else FROM_EMAIL
        
        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": from_addr,
                    "to": lead.email,
                    "subject": campaign.subject_line,
                    "html": campaign.email_template,
                }
            )
            response_data = response.json()
            
            email_log = EmailLog(
                id=str(uuid.uuid4()),
                campaign_id=campaign_id,
                lead_id=lead.id,
                recipient_email=lead.email,
                subject=campaign.subject_line,
                body=campaign.email_template,
                status=EmailStatus.SENT,
                resend_email_id=response_data.get('id', '')
            )
            db.add(email_log)
            sent += 1
            print(f"✅ Sent to {lead.email}")
        except Exception as e:
            print(f"❌ Failed to send to {lead.email}: {e}")
    
    campaign.emails_sent += sent
    db.commit()
    
    return {
        "sent": sent,
        "total": len(leads),
        "message": f"Sent {sent}/{len(leads)} emails"
    }

@router.get("/{campaign_id}/email-logs")
def get_email_logs(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get email logs for a campaign"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    logs = db.query(EmailLog).filter(EmailLog.campaign_id == campaign_id).all()
    
    return [
        {
            "id": log.id,
            "lead_id": log.lead_id,
            "recipient_email": log.recipient_email,
            "subject": log.subject,
            "status": log.status,
            "sent_at": log.sent_at,
            "opened_at": log.opened_at,
            "replied_at": log.replied_at,
            "reply_text": log.reply_text
        }
        for log in logs
    ]