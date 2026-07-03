from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from jose import jwt, JWTError
import uuid
import os

from models import Notification, User, get_db

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

class NotificationPreferencesRequest(BaseModel):
    notify_on_reply: bool
    notify_on_booking: bool

@router.get("/preferences")
def get_notification_preferences(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get user's notification preferences"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "notify_on_reply": user.notify_on_reply,
        "notify_on_booking": user.notify_on_booking
    }

@router.put("/preferences")
def update_notification_preferences(
    request: NotificationPreferencesRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Update user's notification preferences"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.notify_on_reply = request.notify_on_reply
    user.notify_on_booking = request.notify_on_booking
    db.commit()
    
    return {
        "message": "Notification preferences updated",
        "notify_on_reply": user.notify_on_reply,
        "notify_on_booking": user.notify_on_booking
    }

@router.get("/")
def get_notifications(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    unread_only: bool = False
):
    """Get all notifications for user"""
    query = db.query(Notification).filter(Notification.user_id == user_id)
    
    if unread_only:
        query = query.filter(Notification.read == False)
    
    notifications = query.order_by(Notification.created_at.desc()).all()
    
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "read": n.read,
            "related_campaign_id": n.related_campaign_id,
            "related_booking_id": n.related_booking_id,
            "created_at": n.created_at
        }
        for n in notifications
    ]

@router.put("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Mark a notification as read"""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user_id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.read = True
    db.commit()
    
    return {"message": "Notification marked as read"}

@router.put("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Mark all notifications as read"""
    notifications = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.read == False
    ).all()
    
    for n in notifications:
        n.read = True
    
    db.commit()
    
    return {"message": f"Marked {len(notifications)} notifications as read"}

@router.delete("/{notification_id}")
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Delete a notification"""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user_id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    db.delete(notification)
    db.commit()
    
    return {"message": "Notification deleted"}

def create_notification(
    db: Session,
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    related_campaign_id: str = None,
    related_booking_id: str = None
):
    """Helper function to create a notification"""
    notification = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        related_campaign_id=related_campaign_id,
        related_booking_id=related_booking_id
    )
    db.add(notification)
    db.commit()
    return notification