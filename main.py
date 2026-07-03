from dotenv import load_dotenv
import os

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import init_db
from routes import auth, campaigns, templates, webhooks, bookings, admin, teams, followups, notifications, billing
from scheduler import start_scheduler

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://revenue-recovery-frontend-growth-house.vercel.app",
        "https://growthhousepro.vercel.app",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(bookings.router, prefix="/api/bookings", tags=["bookings"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(followups.router, prefix="/api/followups", tags=["followups"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])

scheduler = start_scheduler()

@app.get("/")
def read_root():
    return {"message": "GrowthHouse API is running"}

@app.on_event("shutdown")
def shutdown_scheduler():
    if scheduler and scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] Background scheduler stopped")