from pydantic import BaseModel, Field, conint
from typing import List, Optional, Literal, Annotated

class ToneSliders(BaseModel):
    formality: Annotated[int, Field(ge=0, le=100)] = 50
    empathy: Annotated[int, Field(ge=0, le=100)] = 50
    assertiveness: Annotated[int, Field(ge=0, le=100)] = 50
    transparency: Annotated[int, Field(ge=0, le=100)] = 50

class VoiceProfile(BaseModel):
    brand_name: Optional[str] = None
    language: Literal["uk", "en"] = "uk"

    sliders: ToneSliders = ToneSliders()
    do: List[str] = Field(default_factory=list, max_length=30)
    dont: List[str] = Field(default_factory=list, max_length=30)

    forbidden_phrases: List[str] = Field(default_factory=list, max_length=50)
    preferred_terms: List[str] = Field(default_factory=list, max_length=50)

    example_messages: List[str] = Field(default_factory=list, max_length=10)