"""Category schemas — sourced from static categories.json file."""
from pydantic import BaseModel


class OptionResponse(BaseModel):
    id: int
    label: str
    is_typical: bool
    display_order: int


class CategoryResponse(BaseModel):
    id: int
    name: str
    display_order: int
    options: list[OptionResponse] = []
