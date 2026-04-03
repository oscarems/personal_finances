from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, Integer, String, UniqueConstraint

from finance_app.database import Base


class EmailScrapeTransaction(Base):
    __tablename__ = "email_scrape_transactions"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_email_scrape_transactions_message_id"),
    )

    id = Column(Integer, primary_key=True)
    message_id = Column(String(255), nullable=False)
    transaction_date = Column(Date)
    transaction_datetime = Column(DateTime)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)
    account_label = Column(String(120), nullable=False)
    movement_class = Column(String(120))
    location = Column(String(255))
    sender = Column(String(500), nullable=True)  # campo From: del correo original
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
            "transaction_datetime": self.transaction_datetime.isoformat() if self.transaction_datetime else None,
            "amount": self.amount,
            "currency": self.currency,
            "account_label": self.account_label,
            "movement_class": self.movement_class,
            "location": self.location,
            "sender": self.sender,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
