from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from jose import jwt, JWTError
import uuid
import os
from anthropic import Anthropic

from models import (
    Booking, EmailLog, Campaign, User, get_db
)
from routes.notifications import create_notification

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

client = Anthropic()

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

class AnalyzeReplyRequest(BaseModel):
    email_log_id: str
    reply_text: str

class ConfirmBookingRequest(BaseModel):
    booking_id: str

@router.post("/analyze-reply")
def analyze_reply(
    request: AnalyzeReplyRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Analyze email reply to detect booking requests"""
    
    email_log = db.query(EmailLog).filter(EmailLog.id == request.email_log_id).first()
    if not email_log:
        raise HTTPException(status_code=404, detail="Email log not found")
    
    campaign = db.query(Campaign).filter(Campaign.id == email_log.campaign_id).first()
    if not campaign or campaign.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    prompt = f"""Analyze this email reply and determine if it's a booking request (customer wants to schedule/meet/get service).

Email reply: {request.reply_text}

Respond with ONLY a JSON object (no markdown, no code blocks):
{{"is_booking_request": true/false, "summary": "brief explanation"}}"""

    try:
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text.strip()
        
        import json
        analysis = json.loads(response_text)
        
        is_booking = analysis.get("is_booking_request", False)
        
        # Check if booking already exists
        existing_booking = db.query(Booking).filter(
            Booking.email_log_id == request.email_log_id
        ).first()
        
        if not existing_booking and is_booking:
            booking = Booking(
                id=str(uuid.uuid4()),
                campaign_id=email_log.campaign_id,
                lead_id=email_log.lead_id,
                email_log_id=request.email_log_id,
                lead_email=email_log.recipient_email,
                reply_text=request.reply_text,
                is_booking_request=True,
                confirmed=False
            )
            db.add(booking)
            db.commit()
        
        return {
            "analysis": analysis,
            "is_booking_request": is_booking
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.post("/confirm-booking")
def confirm_booking(
    request: ConfirmBookingRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Confirm a booking and charge the fee"""
    
    booking = db.query(Booking).filter(Booking.id == request.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    campaign = db.query(Campaign).filter(Campaign.id == booking.campaign_id).first()
    if not campaign or campaign.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Mark as confirmed
    booking.confirmed = True
    booking.confirmed_at = __import__('datetime').datetime.utcnow()
    
    # Apply charge
    if campaign.charge_booking_fee and not booking.charge_applied:
        booking.charge_applied = True
    
    # Increment campaign bookings
    campaign.bookings_confirmed += 1
    
    db.commit()
    
    # Create notification
    create_notification(
        db,
        user_id,
        "booking_confirmed",
        "Booking Confirmed! 🎉",
        f"Booking confirmed for {booking.lead_email}. Booking fee of $25 applied.",
        related_campaign_id=campaign.id,
        related_booking_id=booking.id
    )
    
    return {
        "message": "Booking confirmed and charge applied",
        "booking_id": booking.id,
        "confirmed": booking.confirmed,
        "charge_applied": booking.charge_applied,
        "campaign_bookings": campaign.bookings_confirmed
    }

@router.get("/campaign/{campaign_id}")
def get_campaign_bookings(
    campaign_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get all bookings for a campaign"""
    
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or campaign.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    bookings = db.query(Booking).filter(Booking.campaign_id == campaign_id).all()
    
    return [
        {
            "id": b.id,
            "lead_email": b.lead_email,
            "is_booking_request": b.is_booking_request,
            "confirmed": b.confirmed,
            "charge_applied": b.charge_applied,
            "created_at": b.created_at,
            "confirmed_at": b.confirmed_at
        }
        for b in bookings
    ]

@router.get("/")
def get_all_bookings(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get all bookings for user's campaigns"""
    
    campaigns = db.query(Campaign).filter(Campaign.user_id == user_id).all()
    campaign_ids = [c.id for c in campaigns]
    
    bookings = db.query(Booking).filter(Booking.campaign_id.in_(campaign_ids)).all()
    
    return [
        {
            "id": b.id,
            "campaign_id": b.campaign_id,
            "lead_email": b.lead_email,
            "is_booking_request": b.is_booking_request,
            "confirmed": b.confirmed,
            "charge_applied": b.charge_applied,
            "created_at": b.created_at,
            "confirmed_at": b.confirmed_at
        }
        for b in bookings
    ]