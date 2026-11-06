from sqlalchemy.orm import Session

from app.models import RequestEvent, RoutingStage


def record_event(
    db: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    request_id: int | None = None,
    batch_id: int | None = None,
    from_stage: RoutingStage | None = None,
    to_stage: RoutingStage | None = None,
    note: str | None = None,
) -> None:
    db.add(
        RequestEvent(
            request_id=request_id,
            batch_id=batch_id,
            actor_user_id=actor_user_id,
            from_stage=from_stage,
            to_stage=to_stage,
            action=action,
            note=note,
        )
    )