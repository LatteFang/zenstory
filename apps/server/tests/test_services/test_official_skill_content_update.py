"""Official content-only maintenance preserves the DB identity users reference."""
import pytest
from sqlmodel import select

from agent.skills.active_skills import load_active_skills, resolve_selected_skills
from agent.skills.context_injector import SkillContextInjector
from models import PublicSkill, User, UserAddedSkill
from scripts.update_official_skill_content import SkillContentUpdate, apply_updates


def make_rows(session):
    user = User(email="content-update@example.com", username="contentupdate", hashed_password="hash")
    session.add(user)
    session.commit()
    official = PublicSkill(name="Existing", description="Before", instructions="Before instructions", source="official", status="approved", add_count=19, category="plot", tags='["old"]', skill_metadata='{"license":"MIT"}')
    community = PublicSkill(name="Existing", description="Community", instructions="Community instructions", source="community", status="approved")
    session.add_all([official, community])
    session.commit()
    link = UserAddedSkill(user_id=user.id, public_skill_id=official.id, custom_name="My name")
    session.add(link)
    session.commit()
    return user, official, community, link


def update_for(skill):
    return SkillContentUpdate(id=skill.id, name=skill.name, expected_description=skill.description, expected_instructions=skill.instructions, description="After", instructions="After instructions")


def test_content_update_reaches_existing_activation_without_reseeding(db_session):
    user, official, community, link = make_rows(db_session)
    identity = (official.id, official.name, official.category, official.tags, official.skill_metadata, official.add_count, official.status, link.id, link.custom_name)
    apply_updates(db_session, [update_for(official)])
    db_session.commit()
    db_session.expire_all()
    active = load_active_skills(db_session, user.id)
    assert [(s.name, s.instructions) for s in active] == [("My name", "After instructions")]
    assert resolve_selected_skills(db_session, user.id, [link.id])[0].instructions == "After instructions"
    assert "After" in SkillContextInjector().build_skill_catalog(db_session, user.id)
    assert community.instructions == "Community instructions"
    assert identity == (official.id, official.name, official.category, official.tags, official.skill_metadata, official.add_count, official.status, link.id, link.custom_name)
    assert len(db_session.exec(select(PublicSkill)).all()) == 2


@pytest.mark.parametrize("change", ["source", "status", "name", "instructions", "description"])
def test_changed_snapshot_or_wrong_identity_is_rejected(db_session, change):
    _, official, _, _ = make_rows(db_session)
    patch = update_for(official)
    setattr(official, change, "changed")
    db_session.add(official)
    db_session.commit()
    with pytest.raises(ValueError):
        apply_updates(db_session, [patch])
    db_session.rollback()
    assert getattr(official, change) == "changed"


def test_duplicate_ids_are_rejected(db_session):
    _, official, _, _ = make_rows(db_session)
    patch = update_for(official)
    with pytest.raises(ValueError):
        apply_updates(db_session, [patch, patch])
    assert official.instructions == "Before instructions"


def test_entire_batch_is_validated_before_any_row_is_changed(db_session):
    _, official, community, _ = make_rows(db_session)
    with pytest.raises(ValueError):
        apply_updates(db_session, [update_for(official), update_for(community)])
    db_session.rollback()
    assert official.instructions == "Before instructions"
    assert community.instructions == "Community instructions"
