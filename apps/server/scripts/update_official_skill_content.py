#!/usr/bin/env python3
"""Apply a reviewed, snapshot-matched content patch to existing official DB skills.

No catalog/default content is bundled. Dry-run is the default. The caller owns
one transaction for the entire patch; identities, metadata and user links stay.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel, ConfigDict, Field  # noqa: E402
from sqlalchemy import update  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from config.datetime_utils import utcnow  # noqa: E402
from models import PublicSkill  # noqa: E402


class SkillContentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    expected_description: str | None
    expected_instructions: str
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = Field(min_length=1)


def apply_updates(session: Session, patches: list[SkillContentUpdate]) -> list[dict]:
    """Validate the complete snapshot, then CAS text only; caller commits/rolls back."""
    if not patches or len({patch.id for patch in patches}) != len(patches):
        raise ValueError("Patch must contain distinct existing skill IDs")
    before = []
    for patch in patches:
        skill = session.exec(select(PublicSkill).where(PublicSkill.id == patch.id)).first()
        if not skill or (skill.source, skill.status, skill.name, skill.description, skill.instructions) != (
            "official", "approved", patch.name, patch.expected_description, patch.expected_instructions,
        ):
            raise ValueError(f"Official skill snapshot mismatch: {patch.id}")
        before.append(skill.model_dump(mode="json"))

    for patch in patches:
        result = session.exec(
            update(PublicSkill).where(
                PublicSkill.id == patch.id,
                PublicSkill.source == "official",
                PublicSkill.status == "approved",
                PublicSkill.name == patch.name,
                PublicSkill.description == patch.expected_description,
                PublicSkill.instructions == patch.expected_instructions,
            ).values(description=patch.description, instructions=patch.instructions, updated_at=utcnow())
        )
        if result.rowcount != 1:
            raise ValueError(f"Official skill changed during update: {patch.id}")
    return before


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patch", type=Path, help="Reviewed JSON array of content updates")
    parser.add_argument("--apply", action="store_true", help="Commit; otherwise validate and roll back")
    parser.add_argument("--backup", type=Path, help="Required for --apply; new private backup file")
    args = parser.parse_args()
    if args.apply and args.backup is None:
        parser.error("--apply requires --backup")
    patches = [SkillContentUpdate.model_validate(row) for row in json.loads(args.patch.read_text())]

    from database import sync_engine

    with Session(sync_engine) as session, session.begin():
        before = apply_updates(session, patches)
        if not args.apply:
            session.rollback()
        else:
            fd = os.open(args.backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as backup:
                json.dump(before, backup, ensure_ascii=False, indent=2)
    print(json.dumps({"applied": args.apply, "matched_skills": len(patches)}))


if __name__ == "__main__":
    main()
