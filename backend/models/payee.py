from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base

class Payee(Base):
    __tablename__ = 'payees'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    default_category_id = Column(Integer, ForeignKey('categories.id'))

    # Relationships
    default_category = relationship('Category', back_populates='payees')
    transactions = relationship('Transaction', back_populates='payee', lazy=True)

    def __repr__(self):
        return f'<Payee {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'default_category_id': self.default_category_id
        }
