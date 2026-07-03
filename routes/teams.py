from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from jose import jwt, JWTError
import uuid
import os

from models import User, Team, TeamMember, TeamRole, get_db

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

class InviteTeamMemberRequest(BaseModel):
    email: str
    team_role: str

@router.get("/team")
def get_team(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get current user's team info"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.team_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = db.query(Team).filter(Team.id == user.team_id).first()
    
    return {
        "id": team.id,
        "name": team.name,
        "owner_id": team.owner_id,
        "created_at": team.created_at
    }

@router.get("/team/members")
def get_team_members(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get all team members"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.team_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    members = db.query(TeamMember).filter(TeamMember.team_id == user.team_id).all()
    
    result = []
    for member in members:
        member_user = db.query(User).filter(User.id == member.user_id).first()
        result.append({
            "id": member.id,
            "user_id": member.user_id,
            "email": member_user.email if member_user else "Unknown",
            "team_role": member.team_role.value,
            "joined_at": member.joined_at
        })
    
    return result

@router.post("/team/invite")
def invite_team_member(
    request: InviteTeamMemberRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Invite a new team member"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.team_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Check if inviter is owner or manager
    inviter_member = db.query(TeamMember).filter(
        TeamMember.team_id == user.team_id,
        TeamMember.user_id == user_id
    ).first()
    
    if not inviter_member or inviter_member.team_role not in [TeamRole.OWNER, TeamRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Only owners/managers can invite members")
    
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    
    if existing_user:
        # User already has account, check if already in team
        existing_member = db.query(TeamMember).filter(
            TeamMember.team_id == user.team_id,
            TeamMember.user_id == existing_user.id
        ).first()
        
        if existing_member:
            raise HTTPException(status_code=400, detail="User already in team")
        
        # Add to team
        new_member = TeamMember(
            id=str(uuid.uuid4()),
            team_id=user.team_id,
            user_id=existing_user.id,
            team_role=TeamRole[request.team_role.upper()],
            invited_by=user_id
        )
        existing_user.team_id = user.team_id
        db.add(new_member)
        db.commit()
        
        return {
            "message": "Member invited successfully",
            "email": request.email,
            "team_role": request.team_role
        }
    else:
        # User doesn't exist - create pending invitation
        # For now, just create a placeholder user with a flag
        # In production, you'd send an email with a unique invite link
        raise HTTPException(status_code=400, detail="User must create an account first. Share your team invite link.")

@router.put("/team/member/{member_id}/role")
def update_member_role(
    member_id: str,
    new_role: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Update a team member's role"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.team_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Check if requester is owner
    requester_member = db.query(TeamMember).filter(
        TeamMember.team_id == user.team_id,
        TeamMember.user_id == user_id
    ).first()
    
    if not requester_member or requester_member.team_role != TeamRole.OWNER:
        raise HTTPException(status_code=403, detail="Only owners can change roles")
    
    member = db.query(TeamMember).filter(TeamMember.id == member_id).first()
    if not member or member.team_id != user.team_id:
        raise HTTPException(status_code=404, detail="Member not found")
    
    member.team_role = TeamRole[new_role.upper()]
    db.commit()
    
    return {
        "message": "Role updated",
        "member_id": member_id,
        "new_role": new_role
    }

@router.delete("/team/member/{member_id}")
def remove_team_member(
    member_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Remove a team member"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.team_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Check if requester is owner
    requester_member = db.query(TeamMember).filter(
        TeamMember.team_id == user.team_id,
        TeamMember.user_id == user_id
    ).first()
    
    if not requester_member or requester_member.team_role != TeamRole.OWNER:
        raise HTTPException(status_code=403, detail="Only owners can remove members")
    
    member = db.query(TeamMember).filter(TeamMember.id == member_id).first()
    if not member or member.team_id != user.team_id:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Can't remove self
    if member.user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    
    # Can't remove owner
    if member.team_role == TeamRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot remove owner")
    
    db.delete(member)
    db.commit()
    
    return {"message": "Member removed"}