from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from finance_app.database import Base
from datetime import datetime


class EmailSenderRule(Base):
    __tablename__ = "email_sender_rules"

    id = Column(Integer, primary_key=True)
    sender_pattern = Column(String(255), nullable=False, unique=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    match_count = Column(Integer, default=1)
    last_seen = Column(DateTime, default=datetime.utcnow)
    confirmed_by_user = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account")

    def to_dict(self):
        return {
            "id": self.id,
            "sender_pattern": self.sender_pattern,
            "account_id": self.account_id,
            "account_name": self.account.name if self.account else None,
            "match_count": self.match_count,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "confirmed_by_user": self.confirmed_by_user,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
