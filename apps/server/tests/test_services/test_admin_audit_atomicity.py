from sqlmodel import select

from models import User
from models.subscription import AdminAuditLog
from services.admin_audit_service import admin_audit_service


def test_audit_can_be_staged_in_callers_transaction(db_session):
    admin = User(username="review_admin_audit", email="review-audit@example.test", hashed_password="unused", is_superuser=True)
    db_session.add(admin)
    db_session.commit()
    log = admin_audit_service.log_action(db_session, admin.id, "update_user", "user", admin.id, commit=False)
    assert log.id
    db_session.flush()
    assert db_session.exec(select(AdminAuditLog)).first() is not None
    db_session.rollback()
    assert db_session.exec(select(AdminAuditLog)).first() is None
