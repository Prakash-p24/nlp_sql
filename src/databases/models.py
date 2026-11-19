import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


def utcnow(): return datetime.now(timezone.utc)

class TenantDatabase(Base):
    __tablename__ = "tenant_databases"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    db_engine: Mapped[str] = mapped_column(String(64), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    credential_secret_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    default_schema: Mapped[str | None] = mapped_column(String(255))
    ssl_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connection_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tenant_database_name"),)
