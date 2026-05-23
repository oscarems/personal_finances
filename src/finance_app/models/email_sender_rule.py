from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from finance_app.database import Base
from datetime import datetime


class EmailSenderRule(Base):
    __tablename__ = "email_sender_rules"

    id = Column(Integer, primary_key=True)
    sender_pattern = Column(String(255), nullable=False)
    match_type = Column(String(20), nullable=False, default="sender")  # "sender" | "keyword"
    rule_purpose = Column(String(20), nullable=False, default="account")  # "account" | "category"
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    match_count = Column(Integer, default=1)
    last_seen = Column(DateTime, default=datetime.utcnow)
    confirmed_by_user = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account")
    category = relationship("Category")

    def to_dict(self):
        acct = self.account
        cat = self.category
        return {
            "id": self.id,
            "sender_pattern": self.sender_pattern,
            "match_type": self.match_type or "sender",
            "rule_purpose": self.rule_purpose or "account",
            "account_id": self.account_id,
            "account_name": acct.name if acct else None,
            "account_currency": acct.currency.code if acct and acct.currency else None,
            "category_id": self.category_id,
            "category_name": cat.name if cat else None,
            "category_group_name": cat.category_group.name if cat and cat.category_group else None,
            "match_count": self.match_count,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "confirmed_by_user": self.confirmed_by_user,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
