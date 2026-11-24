"""Let a link lay its guest page out by Home Assistant area as well as by type.

group_by is the layout a guest page opens with: "type" (the sections by kind
that every link drew before this, "Lights", "Switches") or "area" (one section
per HA area, "Kitchen", "Garden"). guest_can_regroup lets the guest switch
between the two on their own page; their choice is kept in their browser.

NOT NULL with defaults that reproduce the old page exactly ("type", and the
switch shown), so no reader has to reason about a NULL, the same rule 013-016
follow.

Revision ID: 017
Revises: 016
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> list[str]:
    return [r[1] for r in op.get_bind().exec_driver_sql("PRAGMA table_info(tokens)")]


def upgrade() -> None:
    columns = _columns()
    if "group_by" not in columns:
        op.execute("ALTER TABLE tokens ADD COLUMN group_by TEXT NOT NULL DEFAULT 'type'")
    if "guest_can_regroup" not in columns:
        op.execute(
            "ALTER TABLE tokens ADD COLUMN guest_can_regroup INTEGER NOT NULL DEFAULT 1"
        )


def downgrade() -> None:
    columns = _columns()
    if "guest_can_regroup" in columns:
        op.execute("ALTER TABLE tokens DROP COLUMN guest_can_regroup")
    if "group_by" in columns:
        op.execute("ALTER TABLE tokens DROP COLUMN group_by")
