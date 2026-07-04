from dotenv import load_dotenv
import os

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import init_db
from routes import auth, campaigns, templates, webhooks, bookings, admin, teams, followups, notifications

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

@app.get("/")
def read_root():
    return {"message": "GrowthHouse API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}