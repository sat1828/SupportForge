"""User and ticket schemas."""
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserSchema(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ToolApprovalRequest(BaseModel):
    ticket_id: str
    job_id: str
    approved: bool
    modified_response: str | None = None
