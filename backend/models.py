from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Brief(StrictModel):
    title: str = Field(min_length=1, max_length=80)
    objective: str = Field(min_length=1, max_length=500)
    audience: str = Field(min_length=1, max_length=200)
    tone: str = Field(min_length=1, max_length=150)
    details: str = Field(min_length=1, max_length=500)


class Direction(StrictModel):
    message: str = Field(min_length=1, max_length=1500)
    brief: Brief


class Copy(StrictModel):
    headline: str = Field(min_length=1, max_length=100)
    supporting: str = Field(min_length=1, max_length=350)
    cta: str = Field(min_length=1, max_length=55)


class Design(StrictModel):
    background: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    foreground: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    accent: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    motif: Literal['orbit', 'steps', 'sunburst']
    rationale: str = Field(min_length=1, max_length=600)


class Critique(StrictModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[str] = Field(max_length=12)
    recommendation: str = Field(max_length=1000)


OUTPUTS = {'director': Direction, 'copywriter': Copy, 'designer': Design, 'critic': Critique}
