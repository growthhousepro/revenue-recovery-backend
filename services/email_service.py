import os
import requests
from sqlalchemy.orm import Session
from models import Campaign, Lead, EmailLog, EmailStatus, User
from datetime import datetime
import uuid

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
DEFAULT_FROM_EMAIL = os.getenv("FROM_EMAIL", "sales@gogrowthhouse.com")

def convert_text_to_html(text: str) -> str:
    """Convert plain text to HTML, preserving line breaks and spacing"""
    if '<' in text and '>' in text:
        # Already HTML
        return text
    
    # Split by newlines
    lines = text.split('\n')
    html_parts = []
    current_paragraph = []
    blank_line_count = 0
    
    for line in lines:
        if line.strip():
            # Non-empty line
            blank_line_count = 0
            current_paragraph.append(line.strip())
        else:
            # Empty line
            blank_line_count += 1
            if blank_line_count == 1 and current_paragraph:
                # First blank line ends paragraph
                para_text = '<br>'.join(current_paragraph)
                html_parts.append(f'<p>{para_text}</p>')
                current_paragraph = []
            elif blank_line_count > 1:
                # Additional blank lines become spacing
                html_parts.append('<p>&nbsp;</p>')
    
    # Don't forget the last paragraph
    if current_paragraph:
        para_text = '<br>'.join(current_paragraph)
        html_parts.append(f'<p>{para_text}</p>')
    
    return ''.join(html_parts) if html_parts else '<p>No content</p>'

def send_campaign_emails(campaign_id: str, user_id: str, db: Session):
    """Send emails for a campaign to all leads"""
    
    print(f"=== SEND EMAILS START ===")
    print(f"Campaign ID: {campaign_id}")
    print(f"User ID: {user_id}")
    print(f"RESEND_API_KEY set: {bool(RESEND_API_KEY)}")
    
    if not RESEND_API_KEY:
        print("ERROR: Resend API key not configured")
        return {"error": "Resend API key not configured", "sent": 0, "total": 0}
    
    try:
        # Get user to find their sender email
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"ERROR: User {user_id} not found")
            return {"error": "User not found", "sent": 0, "total": 0}
        
        # Use user's sender email or default
        from_email = user.sender_email if user.sender_email else DEFAULT_FROM_EMAIL
        print(f"FROM_EMAIL: {from_email}")
        
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            print(f"ERROR: Campaign {campaign_id} not found")
            return {"error": "Campaign not found", "sent": 0, "total": 0}
        
        print(f"Campaign found: {campaign.name}")
        
        leads = db.query(Lead).filter(Lead.campaign_id == campaign_id).all()
        print(f"Found {len(leads)} leads")
        
        if not leads:
            print("ERROR: No leads in campaign")
            return {"error": "No leads in campaign", "sent": 0, "total": 0}
        
        sent_count = 0
        failed_count = 0
        
        for idx, lead in enumerate(leads):
            try:
                print(f"\n--- Sending email {idx + 1}/{len(leads)} to {lead.email} ---")
                
                # Replace template variables
                body = campaign.email_template
                body = body.replace("{first_name}", lead.first_name or "")
                body = body.replace("{last_name}", lead.last_name or "")
                body = body.replace("{company}", lead.company or "")
                
                # Convert plain text to HTML if needed
                body = convert_text_to_html(body)
                
                subject = campaign.subject_line
                subject = subject.replace("{first_name}", lead.first_name or "")
                subject = subject.replace("{last_name}", lead.last_name or "")
                subject = subject.replace("{company}", lead.company or "")
                
                print(f"Subject: {subject}")
                print(f"To: {lead.email}")
                print(f"From: {from_email}")
                print("Calling Resend API...")
                
                response = requests.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {RESEND_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": from_email,
                        "to": lead.email,
                        "subject": subject,
                        "html": body,
                    }
                )
                
                print(f"Resend response status: {response.status_code}")
                print(f"Resend response: {response.text}")
                
                if response.status_code != 200:
                    print(f"ERROR: Resend API returned {response.status_code}")
                    failed_count += 1
                    continue
                
                response_data = response.json()
                resend_id = response_data.get("id")
                print(f"Email sent with Resend ID: {resend_id}")
                
                email_id = str(uuid.uuid4())
                email_log = EmailLog(
                    id=email_id,
                    campaign_id=campaign_id,
                    lead_id=lead.id,
                    recipient_email=lead.email,
                    subject=subject,
                    body=body,
                    status=EmailStatus.SENT,
                    sent_at=datetime.utcnow(),
                    resend_email_id=resend_id
                )
                db.add(email_log)
                sent_count += 1
                print(f"✓ Email sent successfully")
                
            except Exception as e:
                print(f"✗ ERROR sending email to {lead.email}: {str(e)}")
                import traceback
                traceback.print_exc()
                failed_count += 1
                continue
        
        print(f"\nUpdating campaign stats: {sent_count} sent, {failed_count} failed")
        campaign.emails_sent += sent_count
        db.commit()
        print("Campaign stats updated")
        
        result = {
            "message": f"Sent {sent_count} emails",
            "sent": sent_count,
            "total": len(leads),
            "failed": failed_count
        }
        print(f"Final result: {result}")
        print("=== SEND EMAILS END ===\n")
        return result
        
    except Exception as e:
        print(f"FATAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        print("=== SEND EMAILS END ===\n")
        return {"error": str(e), "sent": 0, "total": 0}


def handle_reply(email_id: str, from_email: str, to_email: str, subject: str, body: str, db: Session):
    try:
        email_log = db.query(EmailLog).filter(EmailLog.resend_email_id == email_id).first()
        
        if not email_log:
            print(f"Email log not found for {email_id}")
            return {"error": "Email log not found"}
        
        email_log.status = EmailStatus.REPLIED
        email_log.replied_at = datetime.utcnow()
        
        campaign = db.query(Campaign).filter(Campaign.id == email_log.campaign_id).first()
        if campaign:
            campaign.replies_received += 1
        
        db.commit()
        
        return {"message": "Reply recorded", "email_id": email_id}
        
    except Exception as e:
        print(f"Error handling reply: {str(e)}")
        return {"error": str(e)}