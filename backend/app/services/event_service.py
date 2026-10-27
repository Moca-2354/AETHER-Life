from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.event import Event
from app.schemas.event import EventCreate

class EventService:
    def __init__(self, db: Session):
        self.db = db

    def get_events(
        self,
        limit: int = 50,
        offset: int = 0,
        event_type: Optional[str] = None
    ) -> List[Event]:
        query = select(Event).order_by(Event.created_at.desc(), Event.id.desc())
        if event_type:
            query = query.where(Event.event_type == event_type)
        query = query.offset(offset).limit(limit)
        return list(self.db.scalars(query).all())

    def create_event(self, event_in: EventCreate) -> Event:
        event = Event(
            event_type=event_in.event_type,
            description=event_in.description,
            source=event_in.source,
            payload=event_in.payload
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def log_event(
        self,
        event_type: str,
        description: str,
        source: str = "system",
        payload: Optional[str] = None
    ) -> Event:
        event = Event(
            event_type=event_type,
            description=description,
            source=source,
            payload=payload
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event
