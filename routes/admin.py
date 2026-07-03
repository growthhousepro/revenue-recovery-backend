from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from jose import jwt, JWTError
import os

from models import User, Campaign, Booking, UserRole, get_db

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

def verify_admin(user_id: str, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

class ToggleBookingFeeRequest(BaseModel):
    campaign_id: str
    charge_fee: bool

@router.get("/clients")
def get_all_clients(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get all client accounts (admin only)"""
    verify_admin(user_id, db)
    
    clients = db.query(User).filter(User.role == UserRole.CLIENT).all()
    
    return [
        {
            "id": c.id,
            "email": c.email,
            "created_at": c.created_at
        }
        for c in clients
    ]

@router.get("/client/{client_id}/campaigns")
def get_client_campaigns(
    client_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get all campaigns for a specific client (admin only)"""
    verify_admin(user_id, db)
    
    campaigns = db.query(Campaign).filter(Campaign.user_id == client_id).all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "client_name": c.client_name,
            "status": c.status.value,
            "total_leads": c.total_leads,
            "emails_sent": c.emails_sent,
            "replies_received": c.replies_received,
            "bookings_confirmed": c.bookings_confirmed,
            "charge_booking_fee": c.charge_booking_fee,
            "created_at": c.created_at
        }
        for c in campaigns
    ]

@router.post("/toggle-booking-fee")
def toggle_booking_fee(
    request: ToggleBookingFeeRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Toggle booking fee on/off for a campaign (admin only)"""
    verify_admin(user_id, db)
    
    campaign = db.query(Campaign).filter(Campaign.id == request.campaign_id).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    campaign.charge_booking_fee = request.charge_fee
    db.commit()
    
    return {
        "message": f"Booking fee {'enabled' if request.charge_fee else 'disabled'}",
        "campaign_id": campaign.id,
        "charge_booking_fee": campaign.charge_booking_fee
    }

@router.get("/analytics")
def get_analytics(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get total GrowthHouse revenue and analytics (admin only)"""
    verify_admin(user_id, db)
    
    all_campaigns = db.query(Campaign).all()
    
    total_bookings = 0
    total_revenue = 0
    total_leads = 0
    total_emails_sent = 0
    
    for campaign in all_campaigns:
        bookings = db.query(Booking).filter(
            Booking.campaign_id == campaign.id,
            Booking.confirmed == True
        ).count()
        
        total_bookings += bookings
        if campaign.charge_booking_fee:
            total_revenue += bookings * 25
        total_leads += campaign.total_leads
        total_emails_sent += campaign.emails_sent
    
    total_campaigns = len(all_campaigns)
    total_clients = db.query(User).filter(User.role == UserRole.CLIENT).count()
    
    return {
        "total_clients": total_clients,
        "total_campaigns": total_campaigns,
        "total_leads": total_leads,
        "total_emails_sent": total_emails_sent,
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
        "average_revenue_per_campaign": round(total_revenue / total_campaigns, 2) if total_campaigns > 0 else 0,
        "booking_rate": round((total_bookings / total_emails_sent * 100), 2) if total_emails_sent > 0 else 0
    }

@router.get("/client/{client_id}/analytics")
def get_client_analytics(
    client_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get analytics for a specific client (admin only)"""
    verify_admin(user_id, db)
    
    user = db.query(User).filter(User.id == client_id).first()
    
    if not user or user.role != UserRole.CLIENT:
        raise HTTPException(status_code=404, detail="Client not found")
    
    campaigns = db.query(Campaign).filter(Campaign.user_id == client_id).all()
    
    total_bookings = 0
    total_revenue = 0
    total_leads = 0
    total_emails_sent = 0
    
    for campaign in campaigns:
        bookings = db.query(Booking).filter(
            Booking.campaign_id == campaign.id,
            Booking.confirmed == True
        ).count()
        
        total_bookings += bookings
        if campaign.charge_booking_fee:
            total_revenue += bookings * 25
        total_leads += campaign.total_leads
        total_emails_sent += campaign.emails_sent
    
    return {
        "client_email": user.email,
        "total_campaigns": len(campaigns),
        "total_leads": total_leads,
        "total_emails_sent": total_emails_sent,
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
        "booking_rate": round((total_bookings / total_emails_sent * 100), 2) if total_emails_sent > 0 else 0
    }