from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import Base, make_engine
from app.models import PointsEntry, User


def test_file_backed_database_survives_session_boundary(tmp_path):
    database = make_engine(f"sqlite:///{(tmp_path / 'persistence.db').as_posix()}")
    Base.metadata.create_all(database)
    with Session(database) as session:
        session.add(User(email="persist@example.com", password_hash="hash", name="Persisted", referral_code="PERSIST", preferences={"currency": "USD"}))
        session.commit()
        user_id = session.scalar(select(User.id).where(User.email == "persist@example.com"))
        session.add(PointsEntry(user_id=user_id, amount=17, reason="integration", reference_type="test"))
        session.commit()
    database.dispose()

    reopened = make_engine(f"sqlite:///{(tmp_path / 'persistence.db').as_posix()}")
    with Session(reopened) as session:
        user = session.scalar(select(User).where(User.email == "persist@example.com"))
        entry = session.scalar(select(PointsEntry).where(PointsEntry.user_id == user.id))
        assert user.name == "Persisted"
        assert entry.amount == 17
    reopened.dispose()
