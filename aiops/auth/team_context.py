from sqlalchemy import select
from sqlalchemy.orm import Session

from models.team_membership import TeamMembership


def team_roles_for(db: Session, user_id: int) -> dict[int, str]:
    rows = db.execute(
        select(TeamMembership.team_id, TeamMembership.team_role).where(TeamMembership.user_id == user_id)
    ).all()
    return {team_id: team_role for team_id, team_role in rows}
