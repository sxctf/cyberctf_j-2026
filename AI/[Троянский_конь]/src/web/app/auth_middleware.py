"""Standalone task: one running instance is one player session, no sign-in."""


class TeamInfo:
    def __init__(self, team_id=1, team_name="player"):
        self.team_id = team_id
        self.team_name = team_name


_TEAM = TeamInfo()


async def get_optional_team() -> TeamInfo:
    return _TEAM


async def get_required_team() -> TeamInfo:
    return _TEAM
