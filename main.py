from dotenv import load_dotenv
import os

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import init_db
from routes import auth

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

@app.get("/")
def read_root():
    return {"message": "GrowthHouse API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}