from app.models.change_events import (
    ChangeEventKind,
    ChangeEventSource,
)
from app.services.external_change_normalizers import (
    normalize_github,
)


def test_github_push() -> None:
    values = normalize_github(
        event_type="push",
        payload={
            "ref":
                "refs/heads/main",

            "after":
                "abc123",

            "repository": {
                "full_name":
                    "company/service"
            },

            "sender": {
                "login":
                    "developer"
            },

            "head_commit": {
                "id":
                    "abc123",

                "message":
                    "Deploy service",

                "timestamp":
                    (
                        "2026-08-12"
                        "T18:00:00Z"
                    ),
            },

            "commits": [],
        },
        config={
            "environment":
                "production"
        },
    )

    assert len(values) == 1

    event = values[0]

    assert (
        event.source
        == ChangeEventSource.GITHUB
    )

    assert (
        event.kind
        == ChangeEventKind.CODE
    )

    assert (
        event.repository
        == "company/service"
    )

    assert (
        event.commit_sha
        == "abc123"
    )