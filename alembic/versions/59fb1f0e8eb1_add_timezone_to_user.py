"""Add timezone to user

Revision ID: 59fb1f0e8eb1
Revises: 47290ff83364
Create Date: 2026-04-08 00:43:03.452032

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59fb1f0e8eb1'
down_revision: Union[str, Sequence[str], None] = '47290ff83364'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('timezone', sa.String(length=50), nullable=True))
    op.execute("UPDATE users SET timezone = 'UTC'")
    op.alter_column('users', 'timezone', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'timezone')
