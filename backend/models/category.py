from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base

class CategoryGroup(Base):
    __tablename__ = 'category_groups'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0)
    is_income = Column(Boolean, default=False)  # Income vs expense groups

    # Relationships
    categories = relationship('Category', back_populates='category_group',
                                lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<CategoryGroup {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'sort_order': self.sort_order,
            'is_income': self.is_income,
            'categories': [cat.to_dict() for cat in self.categories]
        }


class Category(Base):
    __tablename__ = 'categories'

    id = Column(Integer, primary_key=True)
    category_group_id = Column(Integer, ForeignKey('category_groups.id'), nullable=False)
    name = Column(String(100), nullable=False)
    target_type = Column(String(20))  # 'monthly', 'target_balance', 'debt'
    target_amount = Column(Float)
    sort_order = Column(Integer, default=0)
    is_hidden = Column(Boolean, default=False)

    # Rollover behavior: 'accumulate' (dinero pasa al siguiente mes) o 'reset' (dinero vuelve a Ready to Assign)
    rollover_type = Column(String(20), default='reset')  # 'accumulate' or 'reset'

    # Relationships
    category_group = relationship('CategoryGroup', back_populates='categories')
    transactions = relationship('Transaction', back_populates='category', lazy=True)
    budget_months = relationship('BudgetMonth', back_populates='category',
                                   lazy=True, cascade='all, delete-orphan')
    payees = relationship('Payee', back_populates='default_category', lazy=True)

    def __repr__(self):
        return f'<Category {self.name}>'

    def to_dict(self, include_group=False):
        data = {
            'id': self.id,
            'category_group_id': self.category_group_id,
            'name': self.name,
            'target_type': self.target_type,
            'target_amount': self.target_amount,
            'sort_order': self.sort_order,
            'is_hidden': self.is_hidden,
            'rollover_type': self.rollover_type
        }
        if include_group and self.category_group:
            data['category_group'] = {
                'id': self.category_group.id,
                'name': self.category_group.name
            }
        return data
