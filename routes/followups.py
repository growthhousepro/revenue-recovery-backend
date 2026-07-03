from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt, JWTError
from typing import Optional
import uuid
import os

from models import (
    Campaign, EmailLog, FollowUpEmail, Lead, User, Notification, get_db
)

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

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

class FollowUpConfig(BaseModel):
    follow_up_1_enabled: bool
    follow_up_1_days: int
    follow_up_1_template_id: Optional[str] = None
    follow_up_2_enabled: bool
    follow_up_2_days: int
    follow_up_2_template_id: Optional[str] = None
    follow_up_3_enabled: bool
    follow_up_3_days: int
    follow_up_3_template_id: Optional[str] = None

@router.post("/{campaign_id}/follow-up-settings")
def set_follow_up_settings(
    campaign_id: str,
    request: FollowUpConfig,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Set follow-up email settings for a campaign"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    try:
        # Validate days - Follow-up 1 allows 0-30, others 1-30 or 1-90
        if request.follow_up_1_enabled:
            if request.follow_up_1_days < 0 or request.follow_up_1_days > 30:
                raise HTTPException(status_code=400, detail="Follow-up 1 days must be 0-30")
        
        if request.follow_up_2_enabled:
            if request.follow_up_2_days < 1 or request.follow_up_2_days > 30:
                raise HTTPException(status_code=400, detail="Follow-up 2 days must be 1-30")
        
        if request.follow_up_3_enabled:
            if request.follow_up_3_days < 1 or request.follow_up_3_days > 90:
                raise HTTPException(status_code=400, detail="Follow-up 3 days must be 1-90")
        
        campaign.follow_up_1_enabled = request.follow_up_1_enabled
        campaign.follow_up_1_days = request.follow_up_1_days
        campaign.follow_up_1_template_id = request.follow_up_1_template_id if request.follow_up_1_template_id else None
        
        campaign.follow_up_2_enabled = request.follow_up_2_enabled
        campaign.follow_up_2_days = request.follow_up_2_days
        campaign.follow_up_2_template_id = request.follow_up_2_template_id if request.follow_up_2_template_id else None
        
        campaign.follow_up_3_enabled = request.follow_up_3_enabled
        campaign.follow_up_3_days = request.follow_up_3_days
        campaign.follow_up_3_template_id = request.follow_up_3_template_id if request.follow_up_3_template_id else None
        
        db.commit()
        
        return {
            "message": "Follow-up settings saved",
            "follow_up_1_enabled": campaign.follow_up_1_enabled,
            "follow_up_1_days": campaign.follow_up_1_days,
            "follow_up_2_enabled": campaign.follow_up_2_enabled,
            "follow_up_2_days": campaign.follow_up_2_days,
            "follow_up_3_enabled": campaign.follow_up_3_enabled,
            "follow_up_3_days": campaign.follow_up_3_days,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error saving settings: {str(e)}")

@router.get("/{campaign_id}/follow-up-settings")
def get_follow_up_settings(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get follow-up email settings for a campaign"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    return {
        "follow_up_1_enabled": campaign.follow_up_1_enabled,
        "follow_up_1_days": campaign.follow_up_1_days,
        "follow_up_1_template_id": campaign.follow_up_1_template_id,
        "follow_up_2_enabled": campaign.follow_up_2_enabled,
        "follow_up_2_days": campaign.follow_up_2_days,
        "follow_up_2_template_id": campaign.follow_up_2_template_id,
        "follow_up_3_enabled": campaign.follow_up_3_enabled,
        "follow_up_3_days": campaign.follow_up_3_days,
        "follow_up_3_template_id": campaign.follow_up_3_template_id,
    }

@router.post("/{campaign_id}/schedule-follow-ups")
def schedule_follow_ups(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Manually schedule follow-up emails for a campaign"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Find emails that don't have replies and haven't been followed up yet
    original_emails = db.query(EmailLog).filter(
        EmailLog.campaign_id == campaign_id,
        EmailLog.is_follow_up == False,
        EmailLog.status != "replied"
    ).all()
    
    scheduled_count = 0
    
    for email in original_emails:
        # Schedule follow-up 1
        if campaign.follow_up_1_enabled:
            existing = db.query(FollowUpEmail).filter(
                FollowUpEmail.original_email_log_id == email.id,
                FollowUpEmail.campaign_id == campaign_id
            ).first()
            
            if not existing:
                scheduled_for = email.sent_at + timedelta(days=campaign.follow_up_1_days)
                follow_up = FollowUpEmail(
                    id=str(uuid.uuid4()),
                    campaign_id=campaign_id,
                    original_email_log_id=email.id,
                    lead_id=email.lead_id,
                    scheduled_for=scheduled_for
                )
                db.add(follow_up)
                scheduled_count += 1
        
        # Schedule follow-up 2 (only if follow-up 1 exists and was sent)
        if campaign.follow_up_2_enabled:
            existing_2 = db.query(FollowUpEmail).filter(
                FollowUpEmail.original_email_log_id == email.id,
                FollowUpEmail.campaign_id == campaign_id
            ).first()
            
            if existing_2 and existing_2.sent_at:
                scheduled_for_2 = existing_2.sent_at + timedelta(days=campaign.follow_up_2_days)
                follow_up_2 = FollowUpEmail(
                    id=str(uuid.uuid4()),
                    campaign_id=campaign_id,
                    original_email_log_id=existing_2.id,
                    lead_id=email.lead_id,
                    scheduled_for=scheduled_for_2
                )
                db.add(follow_up_2)
                scheduled_count += 1
    
    db.commit()
    
    return {
        "message": f"Scheduled {scheduled_count} follow-up emails",
        "scheduled_count": scheduled_count
    }

@router.get("/{campaign_id}/pending-follow-ups")
def get_pending_follow_ups(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get pending follow-up emails for a campaign"""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.user_id == user_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    pending = db.query(FollowUpEmail).filter(
        FollowUpEmail.campaign_id == campaign_id,
        FollowUpEmail.sent_at == None
    ).all()
    
    return [
        {
            "id": f.id,
            "lead_id": f.lead_id,
            "scheduled_for": f.scheduled_for,
            "created_at": f.created_at
        }
        for f in pending
    ]