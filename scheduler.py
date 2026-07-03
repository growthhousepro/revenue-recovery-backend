from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from datetime import datetime
import os

from models import SessionLocal, FollowUpEmail, EmailLog, Campaign, Lead, EmailStatus
from resend import Resend

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@example.com")

resend = Resend(api_key=RESEND_API_KEY)

def send_pending_follow_ups():
    """Check for pending follow-ups and send them if due"""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        pending_follow_ups = db.query(FollowUpEmail).filter(
            FollowUpEmail.scheduled_for <= now,
            FollowUpEmail.sent_at == None
        ).all()
        
        if not pending_follow_ups:
            return
        
        print(f"[Scheduler] Found {len(pending_follow_ups)} follow-ups to send")
        
        for follow_up in pending_follow_ups:
            try:
                original_email = db.query(EmailLog).filter(
                    EmailLog.id == follow_up.original_email_log_id
                ).first()
                
                if not original_email:
                    print(f"[Scheduler] Original email not found for follow-up {follow_up.id}")
                    continue
                
                campaign = db.query(Campaign).filter(
                    Campaign.id == follow_up.campaign_id
                ).first()
                
                lead = db.query(Lead).filter(
                    Lead.id == follow_up.lead_id
                ).first()
                
                if not campaign or not lead:
                    print(f"[Scheduler] Campaign or lead not found for follow-up {follow_up.id}")
                    continue
                
                email_template = campaign.email_template
                subject_line = campaign.subject_line
                
                follow_up_count = db.query(FollowUpEmail).filter(
                    FollowUpEmail.original_email_log_id == follow_up.original_email_log_id,
                    FollowUpEmail.sent_at != None
                ).count()
                
                follow_up_number = follow_up_count + 1
                
                if follow_up_number == 1 and campaign.follow_up_1_template_id:
                    from models import EmailTemplate
                    template = db.query(EmailTemplate).filter(
                        EmailTemplate.id == campaign.follow_up_1_template_id
                    ).first()
                    if template:
                        email_template = template.body
                        subject_line = template.subject
                
                elif follow_up_number == 2 and campaign.follow_up_2_template_id:
                    from models import EmailTemplate
                    template = db.query(EmailTemplate).filter(
                        EmailTemplate.id == campaign.follow_up_2_template_id
                    ).first()
                    if template:
                        email_template = template.body
                        subject_line = template.subject
                
                elif follow_up_number == 3 and campaign.follow_up_3_template_id:
                    from models import EmailTemplate
                    template = db.query(EmailTemplate).filter(
                        EmailTemplate.id == campaign.follow_up_3_template_id
                    ).first()
                    if template:
                        email_template = template.body
                        subject_line = template.subject
                
                from models import User
                user = db.query(User).filter(User.id == campaign.user_id).first()
                from_addr = user.sender_email if user and user.sender_email else FROM_EMAIL
                
                response = resend.send({
                    "from": from_addr,
                    "to": lead.email,
                    "subject": subject_line,
                    "html": email_template,
                })
                
                email_log = EmailLog(
                    id=str(__import__('uuid').uuid4()),
                    campaign_id=campaign.id,
                    lead_id=lead.id,
                    recipient_email=lead.email,
                    subject=subject_line,
                    body=email_template,
                    status=EmailStatus.SENT,
                    resend_email_id=response.get('id', ''),
                    is_follow_up=True
                )
                db.add(email_log)
                
                follow_up.sent_at = datetime.utcnow()
                
                print(f"[Scheduler] Sent follow-up #{follow_up_number} to {lead.email}")
                
            except Exception as e:
                print(f"[Scheduler] Error sending follow-up {follow_up.id}: {str(e)}")
                continue
        
        db.commit()
        print(f"[Scheduler] Completed - {len(pending_follow_ups)} follow-ups processed")
        
    except Exception as e:
        print(f"[Scheduler] Error in send_pending_follow_ups: {str(e)}")
    finally:
        db.close()

def start_scheduler():
    """Start the background scheduler"""
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(send_pending_follow_ups, 'interval', minutes=1)
        scheduler.start()
        print("[Scheduler] Background scheduler started - checking every 1 minute")
        return scheduler
    except Exception as e:
        print(f"[Scheduler] Error starting scheduler: {e}")
        return None