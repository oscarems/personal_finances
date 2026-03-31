from datetime import date, datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship

from finance_app.database import Base


class PatrimonioAsset(Base):
    __tablename__ = "patrimonio_asset"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    tipo = Column(String(30), nullable=False)  # inmueble, vehiculo, otro
    valor_adquisicion = Column(Numeric(18, 2), nullable=False)
    fecha_adquisicion = Column(Date, nullable=False)
    tasa_anual = Column(Float, nullable=False, default=0.0)  # apreciación/valorización anual
    depreciation_method = Column(String(40), nullable=True, default="sin_depreciacion")  # sin_depreciacion, linea_recta, saldo_decreciente, doble_saldo_decreciente
    depreciation_rate = Column(Float, nullable=True)
    depreciation_years = Column(Integer, nullable=True)
    depreciation_salvage_value = Column(Numeric(18, 2), nullable=True)
    depreciation_start_date = Column(Date, nullable=True)
    return_rate = Column(Float, nullable=True)  # rendimiento (ej. arriendo como % anual)
    return_amount = Column(Numeric(18, 2), nullable=True)  # ingreso fijo mensual
    moneda_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    notas = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    currency = relationship("Currency")

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "tipo": self.tipo,
            "valor_adquisicion": float(self.valor_adquisicion),
            "fecha_adquisicion": self.fecha_adquisicion.isoformat() if self.fecha_adquisicion else None,
            "tasa_anual": self.tasa_anual,
            "depreciation_method": self.depreciation_method,
            "depreciation_rate": self.depreciation_rate,
            "depreciation_years": self.depreciation_years,
            "depreciation_salvage_value": float(self.depreciation_salvage_value) if self.depreciation_salvage_value is not None else None,
            "depreciation_start_date": self.depreciation_start_date.isoformat() if self.depreciation_start_date else None,
            "return_rate": self.return_rate,
            "return_amount": float(self.return_amount) if self.return_amount is not None else None,
            "moneda_id": self.moneda_id,
            "currency": self.currency.to_dict() if self.currency else None,
            "notas": self.notas,
            "is_active": self.is_active,
        }
