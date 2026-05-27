from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from finance_app.database import Base


class GmailProcessedMessage(Base):
    __tablename__ = "gmail_processed_messages"

    id = Column(Integer, primary_key=True)
    message_id = Column(String(255), unique=True, nullable=False)
    subject = Column(String(500))
    sender = Column(String(500))
    received_at = Column(DateTime)
    body_text = Column(Text)
    processed_at = Column(DateTime, nullable=True)
    skipped = Column(Boolean, default=False)
    transaction_id = Column(Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "subject": self.subject,
            "sender": self.sender,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "preview": (self.body_text or "")[:200],
            "processed": self.processed_at is not None,
            "skipped": bool(self.skipped),
            "transaction_id": self.transaction_id,
        }
