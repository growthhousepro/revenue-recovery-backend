from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt
import uuid
import os
from passlib.context import CryptContext

from models import User, Team, TeamMember, UserRole, TeamRole, get_db

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(user_id: str, expires_delta: timedelta = None):
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    expire = datetime.utcnow() + expires_delta
    to_encode = {"sub": user_id, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    hashed_password = hash_password(request.password)
    
    # Create user
    new_user = User(
        id=user_id,
        email=request.email,
        hashed_password=hashed_password,
        role=UserRole.CLIENT,
        team_id=team_id
    )
    
    # Create team
    new_team = Team(
        id=team_id,
        owner_id=user_id,
        name=f"{request.email}'s Team"
    )
    
    # Add user as team owner
    team_member = TeamMember(
        id=str(uuid.uuid4()),
        team_id=team_id,
        user_id=user_id,
        team_role=TeamRole.OWNER
    )
    
    db.add(new_user)
    db.add(new_team)
    db.add(team_member)
    db.commit()
    db.refresh(new_user)
    
    access_token = create_access_token(new_user.id)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": new_user.id,
        "email": new_user.email,
        "role": new_user.role.value,
        "team_id": team_id
    }

@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(user.id)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email,
        "role": user.role.value,
        "team_id": user.team_id
    }

@router.get("/me")
def get_me(db: Session = Depends(get_db)):
    from fastapi import Header
    
    authorization: str = Header(None)
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get team role
    team_member = db.query(TeamMember).filter(TeamMember.user_id == user_id, TeamMember.team_id == user.team_id).first()
    team_role = team_member.team_role.value if team_member else None
    
    return {
        "user_id": user.id,
        "email": user.email,
        "role": user.role.value,
        "team_id": user.team_id,
        "team_role": team_role
    }

@router.post("/update-sender-email")
def update_sender_email(request: dict, db: Session = Depends(get_db)):
    from fastapi import Header
    
    authorization: str = Header(None)
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.sender_email = request.get("sender_email")
    user.sender_email_verified = True
    db.commit()
    
    return {"message": "Sender email updated", "sender_email": user.sender_email}