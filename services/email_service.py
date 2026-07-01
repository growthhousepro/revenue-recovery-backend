import os
from resend import Resend
from models import EmailLog, EmailStatus, Campaign, Lead
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

FROM_EMAIL = os.getenv("FROM_EMAIL", "sales@gogrowthhouse.com")

def get_resend_client():
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise ValueError("RESEND_API_KEY not set in environment")
    return Resend(api_key=api_key)

def send_campaign_emails(campaign_id: str, db: Session):
    """Send emails to all leads in a campaign"""
    
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return {"error": "Campaign not found"}
    
    leads = db.query(Lead).filter(Lead.campaign_id == campaign_id).all()
    
    sent_count = 0
    failed_count = 0
    
    resend_client = get_resend_client()
    
    for lead in leads:
        try:
            # Personalize email
            email_body = campaign.email_template.replace("{first_name}", lead.first_name)
            email_body = email_body.replace("{last_name}", lead.last_name)
            email_body = email_body.replace("{company}", lead.company or "")
            
            # Send via Resend
            email = resend_client.emails.send({
                "from": FROM_EMAIL,
                "to": lead.email,
                "subject": campaign.subject_line,
                "html": email_body,
                "reply_to": FROM_EMAIL
            })
            
            # Log the email
            email_log_id = str(uuid.uuid4())
            email_log = EmailLog(
                id=email_log_id,
                campaign_id=campaign_id,
                lead_id=lead.id,
                recipient_email=lead.email,
                subject=campaign.subject_line,
                body=email_body,
                status=EmailStatus.SENT,
                sent_at=datetime.utcnow(),
                resend_email_id=email.get("id") if isinstance(email, dict) else str(email)
            )
            
            db.add(email_log)
            
            # Update lead status
            lead.status = "sent"
            
            sent_count += 1
            
        except Exception as e:
            print(f"Failed to send email to {lead.email}: {str(e)}")
            failed_count += 1
            
            # Log failed attempt
            email_log_id = str(uuid.uuid4())
            email_log = EmailLog(
                id=email_log_id,
                campaign_id=campaign_id,
                lead_id=lead.id,
                recipient_email=lead.email,
                subject=campaign.subject_line,
                body="",
                status=EmailStatus.FAILED
            )
            db.add(email_log)
    
    # Update campaign stats
    campaign.emails_sent = sent_count
    
    db.commit()
    
    return {
        "campaign_id": campaign_id,
        "sent": sent_count,
        "failed": failed_count,
        "total": len(leads)
    }

def handle_reply(resend_event: dict, db: Session):
    """Handle incoming email replies via webhook"""
    
    try:
        event_type = resend_event.get("type")
        email_id = resend_event.get("email_id")
        
        # Find the email log
        email_log = db.query(EmailLog).filter(EmailLog.resend_email_id == email_id).first()
        if not email_log:
            return {"status": "email_not_found"}
        
        if event_type == "email.delivered":
            email_log.status = EmailStatus.SENT
            
        elif event_type == "email.opened":
            email_log.status = EmailStatus.OPENED
            email_log.opened_at = datetime.utcnow()
            email_log.open_count += 1
            
            # Update campaign opens
            campaign = db.query(Campaign).filter(Campaign.id == email_log.campaign_id).first()
            if campaign:
                campaign.opens += 1
        
        elif event_type == "email.clicked":
            email_log.click_count += 1
        
        elif event_type == "email.replied":
            email_log.status = EmailStatus.REPLIED
            email_log.replied_at = datetime.utcnow()
            
            # Update campaign replies
            campaign = db.query(Campaign).filter(Campaign.id == email_log.campaign_id).first()
            if campaign:
                campaign.replies_received += 1
        
        elif event_type == "email.bounced":
            email_log.status = EmailStatus.BOUNCED
        
        db.commit()
        return {"status": "processed"}
        
    except Exception as e:
        print(f"Error handling webhook: {str(e)}")
        return {"error": str(e)}