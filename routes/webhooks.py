from fastapi import APIRouter, Request
from sqlalchemy.orm import Session
from models import get_db, SessionLocal
from services.email_service import handle_reply

router = APIRouter()

@router.post("/email-events")
async def handle_email_events(request: Request):
    """Webhook endpoint for Resend email events"""
    
    db = SessionLocal()
    try:
        body = await request.json()
        result = handle_reply(body, db)
        return {"status": "ok", "result": result}
        
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@router.post("/webhook/reply")
async def webhook_reply(request: Request):
    """Alternative webhook endpoint"""
    
    db = SessionLocal()
    try:
        body = await request.json()
        print(f"Received webhook: {body}")
        result = handle_reply(body, db)
        return {"status": "received", "result": result}
        
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()