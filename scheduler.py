from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import requests
from models import FollowUpEmail, EmailLog, Campaign, Lead, get_db
from sqlalchemy import and_

RESEND_API_KEY = "re_your_key_from_env"
FROM_EMAIL = "sales@gogrowthhouse.com"

scheduler = None

def send_pending_follow_ups():
    """Check for pending follow-ups and send them"""
    db = next(get_db())
    try:
        now = datetime.utcnow()
        pending = db.query(FollowUpEmail).filter(
            and_(
                FollowUpEmail.scheduled_for <= now,
                FollowUpEmail.sent_at == None
            )
        ).all()
        
        for follow_up in pending:
            campaign = db.query(Campaign).filter(Campaign.id == follow_up.campaign_id).first()
            lead = db.query(Lead).filter(Lead.id == follow_up.lead_id).first()
            original_email = db.query(EmailLog).filter(EmailLog.id == follow_up.original_email_log_id).first()
            
            if not (campaign and lead and original_email):
                continue
            
            try:
                response = requests.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {RESEND_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": FROM_EMAIL,
                        "to": lead.email,
                        "subject": campaign.subject_line,
                        "html": campaign.email_template,
                    }
                )
                
                if response.status_code in [200, 201]:
                    resend_email_id = response.json().get('id', '')
                    follow_up.sent_at = datetime.utcnow()
                    
                    email_log = EmailLog(
                        campaign_id=campaign.id,
                        lead_id=lead.id,
                        recipient_email=lead.email,
                        subject=campaign.subject_line,
                        body=campaign.email_template,
                        resend_email_id=resend_email_id,
                        is_follow_up=True
                    )
                    db.add(email_log)
                    db.commit()
                    print(f"[Scheduler] Follow-up sent to {lead.email}")
            except Exception as e:
                print(f"[Scheduler] Error sending follow-up: {e}")
                db.rollback()
    except Exception as e:
        print(f"[Scheduler] Error: {e}")
    finally:
        db.close()

def start_scheduler():
    """Start the background scheduler"""
    global scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_pending_follow_ups, 'interval', minutes=1)
    scheduler.start()
    print("[Scheduler] Background scheduler started - checking every 1 minute")
    return scheduler