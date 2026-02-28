from pydantic import BaseModel


class OptionResponse(BaseModel):
    id: int
    label: str
    is_typical: bool
    display_order: int

    class Config:
        from_attributes = True


class CategoryResponse(BaseModel):
    id: int
    name: str
    display_order: int
    options: list[OptionResponse] = []

    class Config:
        from_attributes = True


class CategoryWithProgress(BaseModel):
    id: int
    name: str
    display_order: int
    total_images: int
    completed_images: int
    skipped_images: int

    class Config:
        from_attributes = True
