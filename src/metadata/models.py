import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


def utcnow(): return datetime.now(timezone.utc)

class DatabaseSchema(Base):
    __tablename__ = "database_schemas"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    database_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenant_databases.id"), nullable=False, index=True)
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("database_id", "schema_name", name="uq_database_schema_name"),)

class DatabaseTable(Base):
    __tablename__ = "database_tables"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    database_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenant_databases.id"), nullable=False, index=True)
    schema_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_schemas.id"), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_type: Mapped[str] = mapped_column(String(64), nullable=False)
    technical_description: Mapped[str | None] = mapped_column(String(2000))
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_object_id: Mapped[str | None] = mapped_column(String(255))
    schema_version: Mapped[int | None] = mapped_column(Integer)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("database_id", "schema_id", "table_name", name="uq_database_table_name"),)

class DatabaseColumn(Base):
    __tablename__ = "database_columns"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_tables.id"), nullable=False, index=True)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(128), nullable=False)
    character_max_length: Mapped[int | None] = mapped_column(Integer)
    numeric_precision: Mapped[int | None] = mapped_column(Integer)
    numeric_scale: Mapped[int | None] = mapped_column(Integer)
    is_nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_foreign_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_unique: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_value: Mapped[str | None] = mapped_column(String(1000))
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_column_id: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("table_id", "column_name", name="uq_database_column_name"),)

class DatabaseConstraint(Base):
    __tablename__ = "database_constraints"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_tables.id"), nullable=False, index=True)
    constraint_name: Mapped[str] = mapped_column(String(255), nullable=False)
    constraint_type: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

class DatabaseRelationship(Base):
    __tablename__ = "database_relationships"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    database_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenant_databases.id"), nullable=False, index=True)
    source_table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_tables.id"), nullable=False)
    source_column_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_columns.id"), nullable=False)
    target_table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_tables.id"), nullable=False)
    target_column_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_columns.id"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    constraint_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

class BusinessTableMetadata(Base):
    __tablename__ = "business_table_metadata"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_tables.id"), nullable=False, unique=True)
    business_description: Mapped[str | None] = mapped_column(Text)
    business_purpose: Mapped[str | None] = mapped_column(Text)
    usage_instructions: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

class BusinessColumnMetadata(Base):
    __tablename__ = "business_column_metadata"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    column_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_columns.id"), nullable=False, unique=True)
    business_description: Mapped[str | None] = mapped_column(Text)
    business_definition: Mapped[str | None] = mapped_column(Text)
    usage_instructions: Mapped[str | None] = mapped_column(Text)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sensitivity_level: Mapped[str | None] = mapped_column(String(64))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

class BusinessSynonym(Base):
    __tablename__ = "business_synonyms"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

class DatabaseProcedure(Base):
    __tablename__ = "database_procedures"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    database_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenant_databases.id"), nullable=False, index=True)
    schema_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_schemas.id"), nullable=False, index=True)
    procedure_name: Mapped[str] = mapped_column(String(255), nullable=False)
    procedure_type: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

class ProcedureParameter(Base):
    __tablename__ = "procedure_parameters"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    procedure_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_procedures.id"), nullable=False, index=True)
    parameter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(128), nullable=False)
    parameter_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    has_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_value: Mapped[str | None] = mapped_column(Text)

class BusinessProcedureMetadata(Base):
    __tablename__ = "business_procedure_metadata"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    procedure_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("database_procedures.id"), nullable=False, unique=True)
    business_description: Mapped[str | None] = mapped_column(Text)
    usage_instructions: Mapped[str | None] = mapped_column(Text)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
