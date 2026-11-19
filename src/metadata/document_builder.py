from __future__ import annotations

import uuid
from collections import defaultdict

from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from src.metadata.models import (
    BusinessColumnMetadata,
    BusinessSynonym,
    BusinessTableMetadata,
    DatabaseColumn,
    DatabaseRelationship,
    DatabaseSchema,
    DatabaseTable,
)


def build_schema_documents(
    db: Session,
    tenant_id: uuid.UUID,
    database_id: uuid.UUID,
    *,
    offset: int = 0,
    limit: int = 64,
) -> list[Document]:
    """Build one LangChain document per selected table from stored metadata.

    Table and column names are loaded from PostgreSQL, so this works for
    schemas that were not known when the application was written.
    """
    if limit < 1:
        raise ValueError("limit must be greater than zero")
    if offset < 0:
        raise ValueError("offset cannot be negative")

    tables = db.scalars(
        select(DatabaseTable)
        .join(DatabaseSchema, DatabaseSchema.id == DatabaseTable.schema_id)
        .where(
            DatabaseTable.tenant_id == tenant_id,
            DatabaseTable.database_id == database_id,
            DatabaseTable.is_selected.is_(True),
            DatabaseTable.is_active.is_(True),
            DatabaseSchema.is_selected.is_(True),
        )
        .order_by(DatabaseSchema.schema_name, DatabaseTable.table_name)
        .offset(offset)
        .limit(limit)
    ).all()
    if not tables:
        return []

    table_ids = [table.id for table in tables]
    schemas = {
        schema.id: schema
        for schema in db.scalars(
            select(DatabaseSchema).where(
                DatabaseSchema.id.in_({table.schema_id for table in tables})
            )
        ).all()
    }

    columns = db.execute(
        select(DatabaseColumn, BusinessColumnMetadata)
        .outerjoin(
            BusinessColumnMetadata,
            (BusinessColumnMetadata.column_id == DatabaseColumn.id)
            & (BusinessColumnMetadata.tenant_id == tenant_id),
        )
        .where(DatabaseColumn.table_id.in_(table_ids))
        .order_by(DatabaseColumn.table_id, DatabaseColumn.ordinal_position)
    ).all()
    columns_by_table: dict[uuid.UUID, list[tuple[DatabaseColumn, BusinessColumnMetadata | None]]] = defaultdict(list)
    column_ids: set[uuid.UUID] = set()
    for column, business_column in columns:
        # Avoid indexing the names and descriptions of explicitly sensitive fields.
        if business_column is not None and business_column.is_sensitive:
            continue
        columns_by_table[column.table_id].append((column, business_column))
        column_ids.add(column.id)

    sensitive_column_ids = set(
        db.scalars(
            select(DatabaseColumn.id)
            .join(DatabaseTable, DatabaseTable.id == DatabaseColumn.table_id)
            .join(
                BusinessColumnMetadata,
                BusinessColumnMetadata.column_id == DatabaseColumn.id,
            )
            .where(
                DatabaseTable.tenant_id == tenant_id,
                DatabaseTable.database_id == database_id,
                BusinessColumnMetadata.tenant_id == tenant_id,
                BusinessColumnMetadata.is_sensitive.is_(True),
            )
        ).all()
    )

    table_business = {
        business.table_id: business
        for business in db.scalars(
            select(BusinessTableMetadata).where(
                BusinessTableMetadata.table_id.in_(table_ids),
                BusinessTableMetadata.is_active.is_(True),
                BusinessTableMetadata.tenant_id == tenant_id,
            )
        ).all()
    }

    # Include relationships touching this page, even when the other table is
    # on a different page. This keeps table documents useful in isolation.
    source_table = aliased(DatabaseTable)
    target_table = aliased(DatabaseTable)
    source_column = aliased(DatabaseColumn)
    target_column = aliased(DatabaseColumn)
    source_schema = aliased(DatabaseSchema)
    target_schema = aliased(DatabaseSchema)
    relationship_rows = db.execute(
        select(
            DatabaseRelationship,
            source_table.table_name,
            target_table.table_name,
            source_schema.schema_name,
            target_schema.schema_name,
            source_column.column_name,
            target_column.column_name,
        )
        .join(source_table, source_table.id == DatabaseRelationship.source_table_id)
        .join(target_table, target_table.id == DatabaseRelationship.target_table_id)
        .join(source_column, source_column.id == DatabaseRelationship.source_column_id)
        .join(target_column, target_column.id == DatabaseRelationship.target_column_id)
        .join(source_schema, source_schema.id == source_table.schema_id)
        .join(target_schema, target_schema.id == target_table.schema_id)
        .where(
            DatabaseRelationship.tenant_id == tenant_id,
            DatabaseRelationship.database_id == database_id,
            DatabaseRelationship.is_active.is_(True),
            *(
                [
                    ~DatabaseRelationship.source_column_id.in_(sensitive_column_ids),
                    ~DatabaseRelationship.target_column_id.in_(sensitive_column_ids),
                ]
                if sensitive_column_ids
                else []
            ),
            (DatabaseRelationship.source_table_id.in_(table_ids)
             | DatabaseRelationship.target_table_id.in_(table_ids)),
        )
    ).all()

    relationships_by_table: dict[uuid.UUID, list[str]] = defaultdict(list)
    for relationship, source_name, target_name, source_schema_name, target_schema_name, source_col, target_col in relationship_rows:
        relation_text = (
            f"{source_schema_name}.{source_name}.{source_col} "
            f"{relationship.relationship_type} "
            f"{target_schema_name}.{target_name}.{target_col}"
        )
        relationships_by_table[relationship.source_table_id].append(relation_text)
        if relationship.target_table_id != relationship.source_table_id:
            relationships_by_table[relationship.target_table_id].append(relation_text)

    resource_ids = table_ids + list(column_ids)
    synonyms_by_resource: dict[uuid.UUID, list[str]] = defaultdict(list)
    if resource_ids:
        synonyms = db.scalars(
            select(BusinessSynonym).where(
                BusinessSynonym.tenant_id == tenant_id,
                BusinessSynonym.resource_id.in_(resource_ids),
            )
        ).all()
        for synonym in synonyms:
            synonyms_by_resource[synonym.resource_id].append(synonym.term)

    documents: list[Document] = []
    for table in tables:
        schema = schemas[table.schema_id]
        qualified_name = f"{schema.schema_name}.{table.table_name}"
        table_meta = table_business.get(table.id)
        lines = [
            f"Schema: {schema.schema_name}",
            f"Table: {table.table_name}",
            f"Qualified table: {qualified_name}",
            f"Table type: {table.table_type}",
        ]
        if schema.description:
            lines.append(f"Schema description: {schema.description}")
        if table.technical_description:
            lines.append(f"Technical description: {table.technical_description}")
        if table_meta:
            if table_meta.business_description:
                lines.append(f"Business description: {table_meta.business_description}")
            if table_meta.business_purpose:
                lines.append(f"Business purpose: {table_meta.business_purpose}")
            if table_meta.usage_instructions:
                lines.append(f"Usage: {table_meta.usage_instructions}")

        table_synonyms = synonyms_by_resource.get(table.id, [])
        if table_synonyms:
            lines.append(f"Also called: {', '.join(sorted(set(table_synonyms)))}")

        table_columns = columns_by_table.get(table.id, [])
        if table_columns:
            lines.append("Columns:")
            for column, business_column in table_columns:
                properties = [column.data_type]
                if column.is_primary_key:
                    properties.append("primary key")
                if column.is_foreign_key:
                    properties.append("foreign key")
                if column.is_unique:
                    properties.append("unique")
                properties.append("nullable" if column.is_nullable else "not nullable")
                line = f"- {column.column_name} ({', '.join(properties)})"
                if business_column:
                    description = business_column.business_definition or business_column.business_description
                    if description:
                        line += f": {description}"
                    if business_column.usage_instructions:
                        line += f" Usage: {business_column.usage_instructions}"
                column_synonyms = synonyms_by_resource.get(column.id, [])
                if column_synonyms:
                    line += f" Also called: {', '.join(sorted(set(column_synonyms)))}"
                lines.append(line)

        table_relationships = sorted(set(relationships_by_table.get(table.id, [])))
        if table_relationships:
            lines.append("Relationships:")
            lines.extend(f"- {relationship}" for relationship in table_relationships)

        documents.append(
            Document(
                page_content="\n".join(lines),
                metadata={
                    "tenant_id": str(tenant_id),
                    "database_id": str(database_id),
                    "schema_id": str(schema.id),
                    "schema_name": schema.schema_name,
                    "table_id": str(table.id),
                    "table_name": table.table_name,
                    "qualified_table_name": qualified_name,
                    "document_type": "table",
                },
            )
        )
    return documents
