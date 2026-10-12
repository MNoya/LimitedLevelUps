from bot.commands.test_group import HALL_OF_FAME
from bot.scripts.fantasy_field_drift import Invitee, field_drift


def test_drift_reports_added_removed_and_changed_invitees():
    unchanged, recountried, added, removed = HALL_OF_FAME[:4]
    seed = [
        {"firstName": "Pro", "lastName": unchanged, "country": "united states", "sources": ["Pro Tour"]},
        {"firstName": "Pro", "lastName": recountried, "country": "France", "sources": ["Pro Tour"]},
        {"firstName": "Pro", "lastName": removed, "country": "Japan", "sources": ["Pro Tour"]},
    ]
    invited = [
        Invitee("Pro", unchanged, "United States", ("Pro Tour",)),
        Invitee("Pro", recountried, "Spain", ("Pro Tour",)),
        Invitee("Pro", added, "Germany", ("Regional",)),
    ]

    findings = field_drift(seed, invited)

    flagged = [finding.split(":")[0] for finding in findings]
    assert flagged == ["country changed", "added", "removed"]
