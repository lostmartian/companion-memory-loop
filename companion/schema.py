from typing import Literal

from pydantic import BaseModel, Field

FactCategory = Literal[
    "relationship", "work", "preference", "plan", "event", "opinion", "other"
]


class Fact(BaseModel):
    subject: str = Field(description="Who or what the fact is about, e.g. 'user'")
    predicate: str = Field(description="Relationship or attribute, e.g. 'works_as', 'dislikes'")
    object: str = Field(description="Value of the attribute, e.g. 'nurse', 'crowded parties'")
    text: str = Field(description="Natural-language statement of the fact")
    category: FactCategory = "other"
    entities: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
