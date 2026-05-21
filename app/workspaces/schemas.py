from pydantic import BaseModel, Field
from datetime import datetime

class ToneOfVoice(BaseModel):
    formality: int = Field(default=50, ge=0, le=100)
    empathy: int = Field(default=50, ge=0, le=100)
    assertiveness: int = Field(default=50, ge=0, le=100)
    transparency: int = Field(default=50, ge=0, le=100)

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    language: str = Field(default="ua", pattern="^(ua|en)$")
    do_rules: list[str] = []
    dont_rules: list[str] = []
    preferred_terms: list[str] = []
    forbidden_phrases: list[str] = []
    example_messages: list[str] = []
    tone_of_voice: ToneOfVoice = ToneOfVoice()

class WorkspaceResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None
    language: str
    do_rules: list[str]
    dont_rules: list[str]
    preferred_terms: list[str]
    forbidden_phrases: list[str]
    example_messages: list[str]
    tone_of_voice: ToneOfVoice
    generating_chat_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        # Reconstruct nested tone_of_voice from flat columns
        if hasattr(obj, "tov_formality"):
            data = {
                "id": obj.id,
                "user_id": obj.user_id,
                "name": obj.name,
                "description": obj.description,
                "language": obj.language,
                "do_rules": obj.do_rules or [],
                "dont_rules": obj.dont_rules or [],
                "preferred_terms": obj.preferred_terms or [],
                "forbidden_phrases": obj.forbidden_phrases or [],
                "example_messages": obj.example_messages or [],
                "generating_chat_id": obj.generating_chat_id,
                "created_at": obj.created_at,
                "updated_at": obj.updated_at,
                "tone_of_voice": {
                    "formality": obj.tov_formality,
                    "empathy": obj.tov_empathy,
                    "assertiveness": obj.tov_assertiveness,
                    "transparency": obj.tov_transparency,
                },
            }
            return cls(**data)
        return super().model_validate(obj, **kwargs)


class WorkspaceRename(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None