"""
Categories API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from backend.database import get_db
from backend.models import Category, CategoryGroup, Transaction, BudgetMonth, Currency

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

class CategoryGroupCreate(BaseModel):
    """Schema for creating a category group"""
    name: str
    is_income: bool = False


@router.post("/groups")
def create_category_group(group_data: CategoryGroupCreate, db: Session = Depends(get_db)):
    """Create a new category group"""
    # Check if group with same name exists
    existing = db.query(CategoryGroup).filter_by(name=group_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Group with this name already exists")

    # Get max sort_order
    max_sort = db.query(CategoryGroup).count()

    new_group = CategoryGroup(
        name=group_data.name,
        is_income=group_data.is_income,
        sort_order=max_sort + 1
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    return {
        "success": True,
        "message": "Group created successfully",
        "group": {
            "id": new_group.id,
            "name": new_group.name,
            "is_income": new_group.is_income
        }
    }


@router.delete("/groups/{group_id}")
def delete_category_group(group_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Delete a category group"""
    group = db.query(CategoryGroup).filter_by(id=group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check if group has categories
    category_count = len(group.categories)
    if category_count > 0 and not force:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Group has categories",
                "categories": category_count,
                "message": "Use force=true to delete anyway (categories will be deleted)"
            }
        )

    # Delete all categories in group
    for category in group.categories:
        db.delete(category)

    db.delete(group)
    db.commit()

    return {
        "success": True,
        "message": "Group deleted",
        "deleted_categories": category_count
    }


@router.post("/seed")
def seed_default_categories(db: Session = Depends(get_db)):
    """
    Create default categories if they don't exist

    This endpoint is useful when the database is empty and needs
    to be populated with default categories for basic usage.

    Returns:
        Summary of categories and groups created
    """
    from config import DEFAULT_CATEGORY_GROUPS

    categories_added = 0
    groups_added = 0

    # Create expense category groups
    for idx, group_data in enumerate(DEFAULT_CATEGORY_GROUPS):
        group = db.query(CategoryGroup).filter_by(name=group_data['name']).first()
        if not group:
            group = CategoryGroup(
                name=group_data['name'],
                sort_order=idx,
                is_income=False
            )
            db.add(group)
            db.flush()  # Get the ID
            groups_added += 1

        # Create categories in this group
        for cat_idx, cat_data in enumerate(group_data['categories']):
            if isinstance(cat_data, str):
                cat_name = cat_data
                rollover_type = 'reset'
            else:
                cat_name = cat_data['name']
                rollover_type = cat_data.get('rollover_type', 'reset')

            category = db.query(Category).filter_by(
                category_group_id=group.id,
                name=cat_name
            ).first()

            if not category:
                category = Category(
                    category_group_id=group.id,
                    name=cat_name,
                    sort_order=cat_idx,
                    rollover_type=rollover_type
                )
                db.add(category)
                categories_added += 1

    # Create Income category group
    income_group = db.query(CategoryGroup).filter_by(name='Ingresos').first()
    if not income_group:
        income_group = CategoryGroup(
            name='Ingresos',
            sort_order=999,
            is_income=True
        )
        db.add(income_group)
        db.flush()
        groups_added += 1

    # Income categories
    income_categories = ['Salario', 'Freelance', 'Inversiones', 'Otros']
    for cat_idx, cat_name in enumerate(income_categories):
        category = db.query(Category).filter_by(
            category_group_id=income_group.id,
            name=cat_name
        ).first()

        if not category:
            category = Category(
                category_group_id=income_group.id,
                name=cat_name,
                sort_order=cat_idx
            )
            db.add(category)
            categories_added += 1

    db.commit()

    # Get total counts after seeding
    total_groups = db.query(CategoryGroup).count()
    total_categories = db.query(Category).filter_by(is_hidden=False).count()

    return {
        "success": True,
        "message": "Default categories seeded successfully",
        "added": {
            "groups": groups_added,
            "categories": categories_added
        },
        "total": {
            "groups": total_groups,
            "categories": total_categories
        }
    }



class CategoryCreate(BaseModel):
    """Schema for creating a category"""
    name: str
    category_group_id: int
    rollover_type: str = 'reset'


class CategoryUpdate(BaseModel):
    """Schema for updating a category"""
    name: Optional[str] = None
    rollover_type: Optional[str] = None
    target_type: Optional[str] = None
    target_amount: Optional[float] = None
    initial_amount: Optional[float] = None
    initial_currency_code: Optional[str] = None


@router.post("/", response_model=CategoryResponse)
def create_category(category: CategoryCreate, db: Session = Depends(get_db)):
    """Create a new category"""
    # Check if category group exists
    group = db.query(CategoryGroup).filter_by(id=category.category_group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Category group not found")

    # Check if category with same name already exists in the group
    existing = db.query(Category).filter_by(
        name=category.name,
        category_group_id=category.category_group_id,
        is_hidden=False
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category with this name already exists in the group")

    # Create category
    new_category = Category(
        name=category.name,
        category_group_id=category.category_group_id,
        rollover_type=category.rollover_type,
        is_hidden=False
    )
    db.add(new_category)
    db.commit()
    db.refresh(new_category)

    return CategoryResponse(
        id=new_category.id,
        name=new_category.name,
        category_group_id=new_category.category_group_id,
        category_group_name=new_category.category_group.name
    )


@router.get("/{category_id}")
def get_category(category_id: int, db: Session = Depends(get_db)):
    """Get a single category with all its details including savings goals"""
    category = db.query(Category).filter_by(id=category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    return category.to_dict(include_group=True)


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, category_update: CategoryUpdate, db: Session = Depends(get_db)):
    """
    Update a category

    Args:
        category_id: ID of the category to update
        category_update: Fields to update

    Returns:
        Updated category
    """
    # Get category
    category = db.query(Category).filter_by(id=category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Update fields
    if category_update.name is not None:
        # Check if new name conflicts with existing categories in the same group
        existing = db.query(Category).filter_by(
            name=category_update.name,
            category_group_id=category.category_group_id,
            is_hidden=False
        ).filter(Category.id != category_id).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Category with this name already exists in the group"
            )
        category.name = category_update.name

    if category_update.rollover_type is not None:
        category.rollover_type = category_update.rollover_type

    if category_update.target_type is not None:
        category.target_type = category_update.target_type

    if category_update.target_amount is not None:
        category.target_amount = category_update.target_amount

    if category_update.initial_amount is not None:
        category.initial_amount = category_update.initial_amount

    if category_update.initial_currency_code is not None:
        if category_update.initial_currency_code == '':
            category.initial_currency_id = None
        else:
            currency = db.query(Currency).filter_by(code=category_update.initial_currency_code).first()
            if not currency:
                raise HTTPException(status_code=400, detail="Invalid initial currency code")
            category.initial_currency_id = currency.id

    db.commit()
    db.refresh(category)

    return CategoryResponse(
        id=category.id,
        name=category.name,
        category_group_id=category.category_group_id,
        category_group_name=category.category_group.name
    )


@router.delete("/{category_id}")
def delete_category(category_id: int, force: bool = False, db: Session = Depends(get_db)):
    """
    Delete a category

    Args:
        category_id: ID of the category to delete
        force: If True, delete even if there are transactions/budgets associated

    Returns:
        Success message with deletion details
    """
    # Get category
    category = db.query(Category).filter_by(id=category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check if category has transactions
    transaction_count = db.query(Transaction).filter_by(category_id=category_id).count()

    # Check if category has budgets
    budget_count = db.query(BudgetMonth).filter_by(category_id=category_id).count()

    if (transaction_count > 0 or budget_count > 0) and not force:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Category has associated data",
                "transactions": transaction_count,
                "budgets": budget_count,
                "message": "Use force=true to delete anyway, or hide the category instead"
            }
        )

    if force:
        # Delete associated budgets
        db.query(BudgetMonth).filter_by(category_id=category_id).delete()

        # Set transactions category to None (uncategorized)
        db.query(Transaction).filter_by(category_id=category_id).update(
            {"category_id": None}
        )
        db.commit()

        # Delete the category
        db.delete(category)
        db.commit()

        return {
            "success": True,
            "message": "Category deleted",
            "deleted": {
                "category": category.name,
                "transactions_uncategorized": transaction_count,
                "budgets_deleted": budget_count
            }
        }
    else:
        # Just hide the category (soft delete)
        category.is_hidden = True
        db.commit()

        return {
            "success": True,
            "message": "Category hidden",
            "category": category.name
        }
