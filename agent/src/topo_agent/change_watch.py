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
        defer_failure_signals: bool = False,
    ) -> None:
        self.client = client

        self.interval_seconds = max(
            interval_seconds,
            10,
        )
        self.defer_failure_signals = (
            defer_failure_signals
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
                failure_signals = (
                    poller.drain_failure_signals()
                    if hasattr(
                        poller,
                        "drain_failure_signals",
                    )
                    else []
                )

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

                failure_response = None

                if (
                    failure_signals
                    and not self.defer_failure_signals
                ):
                    failure_response = (
                        self.client
                        .submit_failure_signals(
                            failure_signals
                        )
                    )

                    if hasattr(
                        poller,
                        "ack_failure_signals",
                    ):
                        poller.ack_failure_signals(
                            failure_signals
                        )

                result[name] = {
                    "status": "success",
                    "observed":
                        len(events),
                    "submitted":
                        response.get(
                            "received_count",
                            0,
                        ),
                    "event_ids": list(
                        response.get(
                            "event_ids",
                            [],
                        )
                    ),
                    "checkpoint_requested": bool(
                        response.get(
                            "checkpoint_requested",
                            False,
                        )
                    ),
                    "checkpoint_reason": (
                        response.get(
                            "checkpoint_reason"
                        )
                    ),
                    "failure_signals": (
                        failure_signals
                        if self.defer_failure_signals
                        else []
                    ),
                    "failure_observed": len(
                        failure_signals
                    ),
                    "failure_submitted": (
                        failure_response.get(
                            "received_count",
                            0,
                        )
                        if failure_response
                        is not None
                        else 0
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

    def ack_failure_signals(
        self,
        signals: list[dict[str, Any]],
    ) -> None:
        for _, poller in self.pollers:
            if hasattr(
                poller,
                "ack_failure_signals",
            ):
                poller.ack_failure_signals(
                    signals
                )

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
