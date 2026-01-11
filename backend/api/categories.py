"""
Categories API endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from backend.database import get_db
from backend.models import Category, CategoryGroup

router = APIRouter()


# Pydantic schemas
class CategoryResponse(BaseModel):
    id: int
    name: str
    category_group_id: int
    category_group_name: str

    class Config:
        from_attributes = True


class CategoryGroupResponse(BaseModel):
    id: int
    name: str
    is_income: bool
    categories: List[dict]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    """Get all categories"""
    categories = db.query(Category).filter_by(is_hidden=False).all()

    return [
        CategoryResponse(
            id=cat.id,
            name=cat.name,
            category_group_id=cat.category_group_id,
            category_group_name=cat.category_group.name if cat.category_group else ""
        )
        for cat in categories
    ]


@router.get("/groups", response_model=List[CategoryGroupResponse])
def get_category_groups(db: Session = Depends(get_db)):
    """Get all category groups with their categories"""
    groups = db.query(CategoryGroup).order_by(CategoryGroup.sort_order).all()

    return [
        CategoryGroupResponse(
            id=group.id,
            name=group.name,
            is_income=group.is_income,
            categories=[
                {'id': cat.id, 'name': cat.name}
                for cat in group.categories if not cat.is_hidden
            ]
        )
        for group in groups
    ]
