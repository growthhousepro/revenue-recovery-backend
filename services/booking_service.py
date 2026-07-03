import anthropic
import json

client = anthropic.Anthropic()

def analyze_reply_for_booking(reply_text: str) -> dict:
    """
    Use Claude to analyze if a reply is a booking request.
    Returns: {
        "is_booking_request": bool,
        "confidence": float (0-1),
        "reason": str,
        "summary": str
    }
    """
    
    prompt = f"""Analyze this email reply to determine if the person is asking to book/schedule a call or meeting.

Email reply:
"{reply_text}"

Respond ONLY with valid JSON (no other text):
{{
    "is_booking_request": true or false,
    "confidence": 0.0 to 1.0,
    "reason": "brief explanation",
    "summary": "one sentence summary of their intent"
}}

Examples of booking requests:
- "Yes, let's schedule a call"
- "When can we meet?"
- "I'm interested, can we book a time?"
- "Let's set up a call to discuss"
- "I'd like to schedule a meeting"

Examples of NOT booking requests:
- "Thanks for reaching out"
- "Send me more information"
- "I'll think about it"
- "Interested but busy right now"
- "What are your rates?"

Return ONLY the JSON object, nothing else."""

    try:
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        response_text = message.content[0].text.strip()
        
        # Parse the JSON response
        result = json.loads(response_text)
        
        return {
            "is_booking_request": result.get("is_booking_request", False),
            "confidence": result.get("confidence", 0),
            "reason": result.get("reason", ""),
            "summary": result.get("summary", "")
        }
        
    except json.JSONDecodeError:
        print(f"Failed to parse Claude response: {response_text}")
        return {
            "is_booking_request": False,
            "confidence": 0,
            "reason": "Error parsing response",
            "summary": ""
        }
    except Exception as e:
        print(f"Error analyzing reply: {e}")
        return {
            "is_booking_request": False,
            "confidence": 0,
            "reason": str(e),
            "summary": ""
        }