from fastapi import APIRouter, HTTPException, Depends, Header, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from jose import jwt, JWTError
import stripe
import os
from datetime import datetime, timedelta
import json

from models import (
    User, Subscription, UsageRecord, Payment, Plan, SubscriptionStatus, get_db
)

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

stripe.api_key = STRIPE_SECRET_KEY

# Pricing
PLAN_PRICES = {
    "launch": 19900,  # $199/month in cents
    "scale": 89900,   # $899/month in cents
}

USAGE_COST = 2  # $0.02 in cents

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

class CreateSubscriptionRequest(BaseModel):
    plan: str  # 'launch' or 'scale'
    email: str
    name: str

class TrackUsageRequest(BaseModel):
    usage_type: str  # 'ai_template' or 'ai_booking_detection'
    campaign_id: str = None
    quantity: int = 1

@router.post("/create-subscription")
def create_subscription(
    request: CreateSubscriptionRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Create or update Stripe subscription"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.team_id:
        raise HTTPException(status_code=400, detail="User is not part of a team")
    
    if request.plan not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    try:
        # Check if user already has a subscription
        existing_sub = db.query(Subscription).filter(
            Subscription.user_id == user_id
        ).first()
        
        if existing_sub and existing_sub.status == SubscriptionStatus.ACTIVE:
            # Update existing subscription
            stripe.Subscription.modify(
                existing_sub.stripe_subscription_id,
                items=[{
                    "id": existing_sub.stripe_subscription_id,
                    "price": get_stripe_price_id(request.plan),
                }],
                billing_cycle_anchor="now",
            )
            existing_sub.plan = request.plan
            existing_sub.updated_at = datetime.utcnow()
            db.commit()
            
            return {
                "message": "Subscription updated",
                "plan": request.plan,
                "status": existing_sub.status
            }
        
        # Create new Stripe customer if doesn't exist
        if not existing_sub or not existing_sub.stripe_customer_id:
            customer = stripe.Customer.create(
                email=request.email,
                name=request.name,
                metadata={"user_id": user_id, "team_id": user.team_id}
            )
            stripe_customer_id = customer.id
        else:
            stripe_customer_id = existing_sub.stripe_customer_id
        
        # Create subscription
        subscription = stripe.Subscription.create(
            customer=stripe_customer_id,
            items=[{
                "price": get_stripe_price_id(request.plan),
            }],
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"],
        )
        
        # Save subscription to database
        new_sub = Subscription(
            user_id=user_id,
            team_id=user.team_id,
            plan=request.plan,
            status=SubscriptionStatus.ACTIVE,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=subscription.id,
            stripe_price_id=get_stripe_price_id(request.plan),
            current_period_start=datetime.fromtimestamp(subscription.current_period_start),
            current_period_end=datetime.fromtimestamp(subscription.current_period_end),
        )
        
        if existing_sub:
            db.delete(existing_sub)
        
        db.add(new_sub)
        db.commit()
        
        return {
            "message": "Subscription created",
            "plan": request.plan,
            "status": subscription.status,
            "client_secret": subscription.latest_invoice.payment_intent.client_secret if subscription.latest_invoice else None
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

@router.get("/subscription")
def get_subscription(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get user's current subscription"""
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).first()
    
    if not subscription:
        return {
            "has_subscription": False,
            "plan": None,
            "status": None
        }
    
    # Calculate usage this month
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
    
    usage = db.query(UsageRecord).filter(
        UsageRecord.user_id == user_id,
        UsageRecord.created_at >= month_start,
        UsageRecord.created_at <= month_end
    ).all()
    
    total_usage_cost = sum(u.cost for u in usage) if usage else 0
    
    return {
        "has_subscription": True,
        "plan": subscription.plan,
        "status": subscription.status,
        "stripe_customer_id": subscription.stripe_customer_id,
        "current_period_start": subscription.current_period_start,
        "current_period_end": subscription.current_period_end,
        "usage_this_month": len(usage),
        "usage_cost_this_month": total_usage_cost / 100,  # convert cents to dollars
    }

@router.post("/track-usage")
def track_usage(
    request: TrackUsageRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Track API usage (AI template generation or booking detection)"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if request.usage_type not in ["ai_template", "ai_booking_detection"]:
        raise HTTPException(status_code=400, detail="Invalid usage type")
    
    # Check if user has active subscription
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.status == SubscriptionStatus.ACTIVE
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=402, detail="No active subscription")
    
    # Track usage
    usage_record = UsageRecord(
        user_id=user_id,
        team_id=user.team_id,
        usage_type=request.usage_type,
        quantity=request.quantity,
        cost=USAGE_COST * request.quantity,
        campaign_id=request.campaign_id,
    )
    
    db.add(usage_record)
    db.commit()
    
    return {
        "message": "Usage tracked",
        "usage_type": request.usage_type,
        "cost": USAGE_COST * request.quantity / 100
    }

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    db = next(get_db())
    
    try:
        # Handle different event types
        if event["type"] == "invoice.paid":
            invoice = event["data"]["object"]
            payment = Payment(
                stripe_invoice_id=invoice["id"],
                stripe_payment_intent_id=invoice.get("payment_intent"),
                amount=invoice["total"],
                status="paid",
                invoice_url=invoice.get("hosted_invoice_url"),
                description=invoice.get("description"),
                billing_reason=invoice.get("billing_reason"),
            )
            # Find subscription and update
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == invoice.get("subscription")
            ).first()
            if subscription:
                payment.user_id = subscription.user_id
                payment.team_id = subscription.team_id
            db.add(payment)
        
        elif event["type"] == "customer.subscription.updated":
            sub = event["data"]["object"]
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == sub["id"]
            ).first()
            if subscription:
                subscription.status = sub["status"]
                subscription.updated_at = datetime.utcnow()
        
        elif event["type"] == "customer.subscription.deleted":
            sub = event["data"]["object"]
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == sub["id"]
            ).first()
            if subscription:
                subscription.status = SubscriptionStatus.CANCELED
                subscription.canceled_at = datetime.utcnow()
                subscription.updated_at = datetime.utcnow()
        
        db.commit()
    except Exception as e:
        print(f"Webhook error: {e}")
    finally:
        db.close()
    
    return {"status": "success"}

def get_stripe_price_id(plan: str) -> str:
    """Get Stripe price ID based on plan"""
    # You'll need to create these prices in Stripe dashboard
    prices = {
        "launch": os.getenv("STRIPE_PRICE_LAUNCH", "price_test_launch"),
        "scale": os.getenv("STRIPE_PRICE_SCALE", "price_test_scale"),
    }
    return prices.get(plan, "price_test_launch")