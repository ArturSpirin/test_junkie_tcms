from sqlalchemy import Select, select
from sqlalchemy.orm import Session


class OrgScopedRepo:
    """Every tenant query goes through here, filtered by the request's org."""

    def __init__(self, db: Session, org_id: str):
        self.db = db
        self.org_id = org_id

    def select(self, model) -> Select:
        return select(model).where(model.org_id == self.org_id)

    def get(self, model, id_: str):
        return self.db.scalar(self.select(model).where(model.id == id_))

    def add(self, obj):
        obj.org_id = self.org_id
        self.db.add(obj)
        return obj
