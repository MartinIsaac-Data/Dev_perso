"""Live meeting bookkeeping.

`meeting_session` was created in 0007 and never written to — the table existed
for a feature that did not. This adds the one column the live window needs and
the index the resume path needs.

**Why a word count and not an offset.** Blocks of audio overlap (ADR-013), so a
new transcript repeats the seam of the previous one and stitching *rewrites the
tail* of what is stored. A character offset recorded before a stitch would point
into the middle of a word after it. A word count survives the rewrite, because
stitching never changes how many complete words precede the seam.

Both changes are additive and the column is `NOT NULL DEFAULT 0`, so the version
of the application running before this migration keeps working against the
schema after it (`Deployment.md` §7).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "meeting_session",
        sa.Column(
            "analysed_words",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # The client asks "do I have a meeting to resume?" on every start, and the
    # answer is one row out of a growing table. Partial on `live` because that
    # is the only status the question is ever asked about, and a meeting spends
    # minutes live against months ended.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS meeting_session_live_idx
        ON meeting_session (user_id, started_at DESC)
        WHERE status = 'live'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS meeting_session_live_idx")
    op.drop_column("meeting_session", "analysed_words")
