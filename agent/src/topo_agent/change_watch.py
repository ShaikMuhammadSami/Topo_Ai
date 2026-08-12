from __future__ import annotations

import logging
import time
from typing import Any


LOGGER = logging.getLogger(
    "topo-agent.change-watch"
)


class ChangeWatchRunner:
    def __init__(
        self,
        *,
        client,
        interval_seconds: int = 30,
    ) -> None:
        self.client = client

        self.interval_seconds = max(
            interval_seconds,
            10,
        )

        self.pollers: list[
            tuple[str, Any]
        ] = []

    def register(
        self,
        name: str,
        poller: Any,
    ) -> None:
        self.pollers.append(
            (
                name,
                poller,
            )
        )

    def run_once(
        self,
    ) -> dict[str, Any]:
        result = {}

        for name, poller in (
            self.pollers
        ):
            try:
                events = poller.poll()

                if events:
                    response = (
                        self.client
                        .submit_change_events(
                            events
                        )
                    )

                else:
                    response = {
                        "received_count": 0,
                        "event_ids": [],
                    }

                result[name] = {
                    "status": "success",
                    "observed":
                        len(events),
                    "submitted":
                        response.get(
                            "received_count",
                            0,
                        ),
                }

            except Exception as exc:
                LOGGER.exception(
                    "Change watcher %s "
                    "failed.",
                    name,
                )

                result[name] = {
                    "status": "failed",
                    "error": str(exc),
                }

        return result

    def run_forever(
        self,
    ) -> None:
        while True:
            result = self.run_once()

            LOGGER.info(
                "Change watch cycle: %s",
                result,
            )

            time.sleep(
                self.interval_seconds
            )