"""
YNAB Category Mapping Model
Maps original YNAB categories to current system categories for metrics/reporting
Does NOT modify transaction data or account balances
"""
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.database import Base


class YnabCategoryMapping(Base):
    __tablename__ = 'ynab_category_mappings'

    id = Column(Integer, primary_key=True)
    ynab_group = Column(String(100), nullable=False)  # Original YNAB group name
    ynab_category = Column(String(100), nullable=False)  # Original YNAB category name
    current_category_id = Column(Integer, ForeignKey('categories.id'))  # Maps to current category

    # Relationships
    current_category = relationship('Category', back_populates='ynab_mappings')

    # Ensure unique mapping per YNAB category
    __table_args__ = (
        UniqueConstraint('ynab_group', 'ynab_category', name='unique_ynab_category'),
    )

    def __repr__(self):
        return f'<YnabCategoryMapping {self.ynab_group}:{self.ynab_category} -> {self.current_category_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'ynab_group': self.ynab_group,
            'ynab_category': self.ynab_category,
            'current_category_id': self.current_category_id,
            'current_category_name': self.current_category.name if self.current_category else None,
            'current_category_group': self.current_category.category_group.name if self.current_category and self.current_category.category_group else None
        }
