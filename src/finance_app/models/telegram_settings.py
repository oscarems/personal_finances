from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from finance_app.database import Base


class TelegramSettings(Base):
    __tablename__ = "telegram_settings"

    id = Column(Integer, primary_key=True)
    bot_token = Column(String(255))
    chat_id = Column(String(120))
    default_account_id = Column(Integer, ForeignKey("accounts.id"))
    default_category_id = Column(Integer, ForeignKey("categories.id"))
    default_currency_id = Column(Integer, ForeignKey("currencies.id"))
    default_transfer_from_account_id = Column(Integer, ForeignKey("accounts.id"))
    default_transfer_to_account_id = Column(Integer, ForeignKey("accounts.id"))
    is_active = Column(Boolean, default=True)
    last_update_id = Column(Integer)
    llm_enabled = Column(Boolean, default=False)
    llm_model = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "default_account_id": self.default_account_id,
            "default_category_id": self.default_category_id,
            "default_currency_id": self.default_currency_id,
            "default_transfer_from_account_id": self.default_transfer_from_account_id,
            "default_transfer_to_account_id": self.default_transfer_to_account_id,
            "is_active": self.is_active,
            "last_update_id": self.last_update_id,
            "llm_enabled": self.llm_enabled,
            "llm_model": self.llm_model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
