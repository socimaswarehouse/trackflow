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


def get_preferred_qr_user(db: Session, user_id: int | None = None) -> User | None:
    if user_id is not None:
        user = get_user_by_id(db, user_id)
        if user is not None and user.is_active:
            return user

    employee_user = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .filter(User.role != "approver")
        .order_by(User.full_name.asc(), User.id.asc())
        .first()
    )
    if employee_user is not None:
        return employee_user

    return (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.full_name.asc(), User.id.asc())
        .first()
    )
