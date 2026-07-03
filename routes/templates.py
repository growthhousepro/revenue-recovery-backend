from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from jose import jwt, JWTError
import uuid
import os
from anthropic import Anthropic

from models import EmailTemplate, User, get_db

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

client_anthropic = Anthropic()

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

class CreateTemplateRequest(BaseModel):
    name: str
    subject: str
    body: str

class GenerateTemplateRequest(BaseModel):
    industry: str
    company_type: str
    campaign_type: str
    call_to_action: str

@router.post("/")
def create_template(
    request: CreateTemplateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Create a custom email template"""
    template_id = str(uuid.uuid4())
    
    new_template = EmailTemplate(
        id=template_id,
        user_id=user_id,
        name=request.name,
        subject=request.subject,
        body=request.body
    )
    
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    
    return {
        "id": new_template.id,
        "name": new_template.name,
        "subject": new_template.subject,
        "body": new_template.body,
        "created_at": new_template.created_at
    }

@router.get("/")
def list_templates(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """List all templates for user"""
    templates = db.query(EmailTemplate).filter(EmailTemplate.user_id == user_id).all()
    
    return [
        {
            "id": t.id,
            "name": t.name,
            "subject": t.subject,
            "body": t.body,
            "created_at": t.created_at
        }
        for t in templates
    ]

@router.get("/{template_id}")
def get_template(
    template_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get a specific template"""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id,
        EmailTemplate.user_id == user_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return {
        "id": template.id,
        "name": template.name,
        "subject": template.subject,
        "body": template.body,
        "created_at": template.created_at
    }

@router.put("/{template_id}")
def update_template(
    template_id: str,
    request: CreateTemplateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Update a template"""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id,
        EmailTemplate.user_id == user_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    template.name = request.name
    template.subject = request.subject
    template.body = request.body
    db.commit()
    
    return {
        "id": template.id,
        "name": template.name,
        "subject": template.subject,
        "body": template.body,
        "updated_at": template.updated_at
    }

@router.delete("/{template_id}")
def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Delete a template"""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id,
        EmailTemplate.user_id == user_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    db.delete(template)
    db.commit()
    
    return {"message": "Template deleted"}

@router.post("/generate/ai")
def generate_template_ai(
    request: GenerateTemplateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Generate email template using Claude AI"""
    
    campaign_type_descriptions = {
        "winback": "A customer who previously used the service but hasn't in a while - they want to win them back",
        "lost_lead": "A lead that went cold and never converted - they want to re-engage them",
        "old_estimate": "Someone who received a quote or estimate but never purchased - they want to remind them",
        "upsell": "An existing customer - they want to sell them a higher-tier service or upgrade",
        "seasonal": "Re-engaging customers during relevant seasons - for seasonal businesses"
    }
    
    campaign_description = campaign_type_descriptions.get(request.campaign_type, "")
    
    prompt = f"""You are an expert email copywriter specializing in local service businesses. Generate a SHORT, HIGH-CONVERSION email template for the following situation:

Context:
- Industry: {request.industry}
- Company Type: {request.company_type}
- Campaign Type: {request.campaign_type.replace('_', ' ').title()}
- Campaign Goal: {campaign_description}
- Desired Call to Action: {request.call_to_action}

CRITICAL: Keep this SHORT and PUNCHY
- Maximum 3-4 short sentences in the body
- Get straight to the point
- 1 clear value proposition specific to the campaign type
- 1 clear call to action
- NO fluff, NO long paragraphs, NO marketing speak
- Feel like it's coming from a real local business owner

Create an email template with:
1. A compelling short subject line (under 50 chars) - tailored to the campaign type
2. A brief opening that acknowledges the situation (e.g., "Last time you needed..." for winback)
3. ONE reason to engage now (specific to the campaign type)
4. The call to action
5. Short professional sign-off with [Your Name] and [Your Business Name]
6. Use [placeholders] for dynamic fields like names, phone numbers, offers

Format your response EXACTLY like this:
SUBJECT: [subject line here]
BODY: [email body here]

The goal is HIGH OPEN RATE and HIGH CLICK-THROUGH RATE. Short wins."""

    try:
        message = client_anthropic.messages.create(
            model="claude-opus-4-6",
            max_tokens=1000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        response_text = message.content[0].text
        
        # Parse response
        lines = response_text.split('\n')
        subject = ""
        body = ""
        
        in_body = False
        for line in lines:
            if line.startswith("SUBJECT:"):
                subject = line.replace("SUBJECT:", "").strip()
            elif line.startswith("BODY:"):
                in_body = True
                body = line.replace("BODY:", "").strip() + "\n"
            elif in_body:
                body += line + "\n"
        
        body = body.strip()
        
        return {
            "subject": subject,
            "body": body,
            "industry": request.industry,
            "company_type": request.company_type,
            "campaign_type": request.campaign_type
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate template: {str(e)}")