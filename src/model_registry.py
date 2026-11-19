"""Import ORM models so SQLAlchemy and Alembic register every application table."""

from src.audit import models as audit_models  # noqa: F401
from src.auth import models as auth_models  # noqa: F401
from src.databases import models as database_models  # noqa: F401
from src.indexing import models as indexing_models  # noqa: F401
from src.metadata import models as metadata_models  # noqa: F401
from src.permissions import models as permission_models  # noqa: F401
from src.rag import models as rag_models  # noqa: F401
from src.tenants import models as tenant_models  # noqa: F401
