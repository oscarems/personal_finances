"""
YNAB Category Mappings API
Manage mappings between YNAB categories and current system categories
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from finance_app.database import get_db
from finance_app.models import YnabCategoryMapping, Category

router = APIRouter()


class YnabMappingCreate(BaseModel):
    ynab_group: str
    ynab_category: str
    current_category_id: int


class YnabMappingUpdate(BaseModel):
    current_category_id: int


@router.get("/")
def list_mappings(db: Session = Depends(get_db)):
    """List all YNAB category mappings"""
    mappings = db.query(YnabCategoryMapping).all()
    return [mapping.to_dict() for mapping in mappings]


@router.get("/unmapped")
def list_unmapped_ynab_categories(db: Session = Depends(get_db)):
    """
    Find YNAB categories in transactions that don't have a mapping yet.
    Uses the import_id field to identify YNAB imports.
    """
    from finance_app.models import Transaction

    # Get all existing mappings
    existing_mappings = db.query(YnabCategoryMapping).all()
    mapped_categories = {
        (m.ynab_group, m.ynab_category): m.current_category_id
        for m in existing_mappings
    }

    # Get all YNAB transactions (those with import_id starting with 'ynab_')
    ynab_transactions = db.query(Transaction).filter(
        Transaction.import_id.like('ynab_%')
    ).all()

    # Extract unique YNAB categories from memo or category
    # Note: This is a simplified version. You may need to adjust based on
    # how you want to store/retrieve original YNAB category info
    unmapped = []
    seen = set()

    for txn in ynab_transactions:
        # Check if transaction has memo with YNAB category info
        # This assumes you might store original category in memo
        # Adjust logic based on your actual data structure
        if txn.category and txn.category.name:
            # For now, return categories that aren't mapped
            key = ("Unknown", txn.category.name)
            if key not in mapped_categories and key not in seen:
                unmapped.append({
                    'ynab_group': 'Unknown',
                    'ynab_category': txn.category.name,
                    'current_category_id': txn.category_id,
                    'current_category_name': txn.category.name,
                    'transaction_count': 1  # Would need aggregation for real count
                })
                seen.add(key)

    return unmapped


@router.post("/")
def create_mapping(mapping: YnabMappingCreate, db: Session = Depends(get_db)):
    """Create a new YNAB category mapping"""

    # Verify category exists
    category = db.query(Category).get(mapping.current_category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check if mapping already exists
    existing = db.query(YnabCategoryMapping).filter(
        YnabCategoryMapping.ynab_group == mapping.ynab_group,
        YnabCategoryMapping.ynab_category == mapping.ynab_category
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Mapping for {mapping.ynab_group}:{mapping.ynab_category} already exists"
        )

    # Create mapping
    new_mapping = YnabCategoryMapping(
        ynab_group=mapping.ynab_group,
        ynab_category=mapping.ynab_category,
        current_category_id=mapping.current_category_id
    )

    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)

    return new_mapping.to_dict()


@router.put("/{mapping_id}")
def update_mapping(
    mapping_id: int,
    mapping_update: YnabMappingUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing YNAB category mapping"""

    # Get existing mapping
    existing_mapping = db.query(YnabCategoryMapping).get(mapping_id)
    if not existing_mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    # Verify new category exists
    category = db.query(Category).get(mapping_update.current_category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Update mapping
    existing_mapping.current_category_id = mapping_update.current_category_id
    db.commit()
    db.refresh(existing_mapping)

    return existing_mapping.to_dict()


@router.delete("/{mapping_id}")
def delete_mapping(mapping_id: int, db: Session = Depends(get_db)):
    """Delete a YNAB category mapping"""

    mapping = db.query(YnabCategoryMapping).get(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.delete(mapping)
    db.commit()

    return {"message": "Mapping deleted successfully"}


@router.post("/bulk-create")
def bulk_create_mappings(
    mappings: List[YnabMappingCreate],
    db: Session = Depends(get_db)
):
    """Create multiple YNAB category mappings at once"""

    created = []
    errors = []

    for mapping in mappings:
        try:
            # Verify category exists
            category = db.query(Category).get(mapping.current_category_id)
            if not category:
                errors.append({
                    'ynab_category': f"{mapping.ynab_group}:{mapping.ynab_category}",
                    'error': 'Category not found'
                })
                continue

            # Check if mapping already exists
            existing = db.query(YnabCategoryMapping).filter(
                YnabCategoryMapping.ynab_group == mapping.ynab_group,
                YnabCategoryMapping.ynab_category == mapping.ynab_category
            ).first()

            if existing:
                # Update existing mapping
                existing.current_category_id = mapping.current_category_id
                db.commit()
                db.refresh(existing)
                created.append(existing.to_dict())
            else:
                # Create new mapping
                new_mapping = YnabCategoryMapping(
                    ynab_group=mapping.ynab_group,
                    ynab_category=mapping.ynab_category,
                    current_category_id=mapping.current_category_id
                )
                db.add(new_mapping)
                db.commit()
                db.refresh(new_mapping)
                created.append(new_mapping.to_dict())

        except Exception as e:
            errors.append({
                'ynab_category': f"{mapping.ynab_group}:{mapping.ynab_category}",
                'error': str(e)
            })

    return {
        'created': created,
        'errors': errors,
        'total': len(created),
        'failed': len(errors)
    }
