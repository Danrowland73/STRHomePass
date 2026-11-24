"""Let a link's guest page take on the look of the guest's phone.

page_style is the look of the guest page:

    "standard"  the HomePass look every link had before this
    "device"    an iOS look on iPhone and iPad, an Android look on Android,
                and the standard look everywhere else
    "ios"       the iOS look on every device
    "android"   the Android look on every device

The device is detected in the guest's browser, before the page paints. Only
looks change: the same controls, the same commands, the same checks.

NOT NULL DEFAULT 'standard' so every existing link looks as it did and no
reader has to reason about a NULL, the same rule 013-017 follow.

Revision ID: 018
Revises: 017
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> list[str]:
    return [r[1] for r in op.get_bind().exec_driver_sql("PRAGMA table_info(tokens)")]


def upgrade() -> None:
    if "page_style" not in _columns():
        op.execute("ALTER TABLE tokens ADD COLUMN page_style TEXT NOT NULL DEFAULT 'standard'")


def downgrade() -> None:
    if "page_style" in _columns():
        op.execute("ALTER TABLE tokens DROP COLUMN page_style")
