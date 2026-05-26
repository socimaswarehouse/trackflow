"""User service queries."""

from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_all_employee_users(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.is_active.is_(True))
        .filter(User.role != "approver")
        .order_by(User.full_name.asc(), User.id.asc())
        .all()
    )
