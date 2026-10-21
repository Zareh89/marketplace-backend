"""add product embedding

Revision ID: 99c553ecd577
Revises: 2e4662e53156
Create Date: 2026-10-21 18:19:32.662150

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR


# revision identifiers, used by Alembic.
revision: str = '99c553ecd577'
down_revision: Union[str, Sequence[str], None] = '2e4662e53156'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate doesn't see Postgres extensions; the `vector` type needs it first.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column('products', sa.Column('embedding', VECTOR(dim=1024), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # The extension is left installed on purpose: it is database-wide and harmless.
    op.drop_column('products', 'embedding')
