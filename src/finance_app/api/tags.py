from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Tag

router = APIRouter()


class TagCreate(BaseModel):
    name: str
    color: str | None = None


@router.get("/")
def list_tags(db: Session = Depends(get_db)):
    return [tag.to_dict() for tag in db.query(Tag).order_by(Tag.name.asc()).all()]


@router.post("/")
def create_tag(payload: TagCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tag name is required")

    existing = db.query(Tag).filter_by(name=name).first()
    if existing:
        return existing.to_dict()

    tag = Tag(name=name, color=payload.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag.to_dict()
