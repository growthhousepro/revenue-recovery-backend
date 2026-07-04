from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os
from models import User, Team, TeamMember, UserRole, TeamRole, get_db

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    team_id: str
    role: str

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = hash_password(request.password)
    
    team = Team(name=f"{request.email}'s Team")
    db.add(team)
    db.flush()
    
    new_user = User(
        email=request.email,
        hashed_password=hashed_password,
        team_id=team.id,
        role=UserRole.ADMIN
    )
    db.add(new_user)
    db.flush()
    
    team_member = TeamMember(
        team_id=team.id,
        user_id=new_user.id,
        role=TeamRole.OWNER
    )
    db.add(team_member)
    db.commit()
    
    access_token = create_access_token({"sub": new_user.id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": new_user.id,
        "email": new_user.email,
        "team_id": team.id,
        "role": new_user.role
    }

@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token({"sub": user.id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email,
        "team_id": user.team_id,
        "role": user.role
    }