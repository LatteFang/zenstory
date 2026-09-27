"""
Seed builtin skills (agent/skills/builtin/<id>/SKILL.md) into the public skill library.

Thin CLI over services.builtin_skill_seed.seed_builtin_skills (idempotent).

Usage:
    # Create missing builtin skills
    python scripts/migrate_skills.py --db-url "postgresql://user:pass@host:port/db"

    # Also overwrite existing builtin skills with the files on disk
    python scripts/migrate_skills.py --db-url "..." --force
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlmodel import Session

from services.builtin_skill_seed import seed_builtin_skills


def migrate_skills(db_url: str, force: bool = False) -> None:
    """Seed builtin skills into the database at db_url."""
    engine = create_engine(db_url)
    with Session(engine) as session:
        result = seed_builtin_skills(session, force=force)

    print("Builtin skills seeded:")
    print(f"  Created: {result['created']}")
    print(f"  Updated: {result['updated']}")
    print(f"  Skipped: {result['skipped']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed builtin skills into the database")
    parser.add_argument(
        "--db-url",
        required=True,
        help="Database URL (PostgreSQL connection string)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing builtin skills",
    )

    args = parser.parse_args()
    migrate_skills(args.db_url, args.force)


if __name__ == "__main__":
    main()
