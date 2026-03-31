from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from finance_app.database import Base
from datetime import datetime

_AUTO_MEMO_PREFIX = "auto:"
_AUTO_MEMO_DEFAULT = "transacción automática"
_PROTECTED_AUTO_KEYWORDS = ("hipoteca", "eps", "pensión", "pension")

class Transaction(Base):
    __tablename__ = 'transactions'
    __table_args__ = (
        UniqueConstraint('source', 'source_id', name='uq_transactions_source_source_id'),
    )

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    date = Column(Date, nullable=False, index=True)
    payee_id = Column(Integer, ForeignKey('payees.id'))
    category_id = Column(Integer, ForeignKey('categories.id'))
    debt_id = Column(Integer, ForeignKey('debts.id'))
    memo = Column(Text)
    amount = Column(Float, nullable=False)  # Positive=inflow, Negative=outflow
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    original_amount = Column(Float, nullable=False)  # Amount as entered by user
    original_currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    fx_rate = Column(Float)  # Conversion rate used when original currency differs
    base_amount = Column(Float)  # Amount converted to base currency
    base_currency_id = Column(Integer, ForeignKey('currencies.id'))
    cleared = Column(Boolean, default=False)  # Reconciliation
    approved = Column(Boolean, default=True)
    transfer_account_id = Column(Integer, ForeignKey('accounts.id'))  # If transfer
    investment_asset_id = Column(Integer, nullable=True)  # legacy column, FK to wealth_assets removed
    is_adjustment = Column(Boolean, default=False)  # Balance adjustment transaction
    import_id = Column(String(100))  # YNAB import ID to avoid duplicates
    source = Column(String(50))
    source_id = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    account = relationship('Account', foreign_keys=[account_id], back_populates='transactions')
    transfer_account = relationship('Account', foreign_keys=[transfer_account_id], overlaps="transfer_transactions")
    payee = relationship('Payee', back_populates='transactions')
    category = relationship('Category', back_populates='transactions')
    debt = relationship('Debt')
    currency = relationship('Currency', foreign_keys=[currency_id], back_populates='transactions')
    # investment_asset relationship removed (WealthAsset model consolidated into Patrimonio)
    tag_links = relationship('TransactionTag', back_populates='transaction', cascade='all, delete-orphan')
    splits = relationship('TransactionSplit', back_populates='transaction', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Transaction {self.date} {self.amount}>'

    def delete_block_reason(self):
        if self.is_adjustment:
            memo = (self.memo or "").strip()
            if memo.startswith("Cubrir exceso:") or memo.startswith("Cubierto desde:"):
                return None  # Budget adjustment pairs can be deleted
            return "No se puede eliminar un ajuste de balance."

        memo = (self.memo or "").strip()
        memo_lower = memo.lower()
        is_auto_generated = memo_lower == _AUTO_MEMO_DEFAULT or memo_lower.startswith(_AUTO_MEMO_PREFIX)

        if is_auto_generated:
            payee_name = (self.payee.name if self.payee else "").lower()
            if any(keyword in memo_lower for keyword in _PROTECTED_AUTO_KEYWORDS) or any(
                keyword in payee_name for keyword in _PROTECTED_AUTO_KEYWORDS
            ):
                return "Transacción automática crítica (hipoteca/EPS/pensión)."

        return None

    def to_dict(self):
        delete_reason = self.delete_block_reason()
        data = {
            'id': self.id,
            'account_id': self.account_id,
            'account_name': self.account.name if self.account else None,
            'date': self.date.isoformat() if self.date else None,
            'payee_id': self.payee_id,
            'payee_name': self.payee.name if self.payee else None,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'debt_id': self.debt_id,
            'debt_name': self.debt.name if self.debt else None,
            'memo': self.memo,
            'amount': self.amount,
            'currency': self.currency.to_dict() if self.currency else None,
            'original_amount': self.original_amount,
            'original_currency_id': self.original_currency_id,
            'fx_rate': self.fx_rate,
            'base_amount': self.base_amount,
            'base_currency_id': self.base_currency_id,
            'cleared': self.cleared,
            'approved': self.approved,
            'transfer_account_id': self.transfer_account_id,
            'investment_asset_id': self.investment_asset_id,
            'investment_asset_name': None,
            'is_adjustment': self.is_adjustment,
            'import_id': self.import_id,
            'source': self.source,
            'source_id': self.source_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'can_delete': delete_reason is None,
            'delete_reason': delete_reason
        }
        data['tags'] = [link.tag.to_dict() for link in self.tag_links if link.tag]
        data['splits'] = [split.to_dict() for split in self.splits]
        return data
