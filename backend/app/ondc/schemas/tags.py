from typing import List
from pydantic import Field
from app.ondc.schemas.base import Text, WireModel


class Tag(WireModel):
    code: Text
    value: str


class TagGroup(WireModel):
    code: Text
    list: List[Tag] = Field(min_length=1)
