from pydantic import BaseModel

class TimeLogCreate(BaseModel):
    user_id: int
    action: str