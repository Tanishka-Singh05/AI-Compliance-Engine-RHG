import os
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    INFO     = "INFO"


@dataclass
class AlertPayload:
    event_type: str
    pipeline_id: str
    repo: str
    environment: str
    severity: AlertSeverity
    findings_count: int
    blocking_rules: list[str]
    decision: str
    report_url: str
    mutation_count: int = 0
    escalation_reason: str = ""


class AlertChannel(Protocol):
    async def send(self, payload: AlertPayload) -> bool: ...


class AlertRouter:
    def __init__(self):
        self.channels: list[AlertChannel] = []

    def register(self, channel: AlertChannel) -> "AlertRouter":
        self.channels.append(channel)
        return self

    async def dispatch(self, payload: AlertPayload) -> None:
        for channel in self.channels:
            try:
                await channel.send(payload)
            except (ConnectionError, TimeoutError, OSError) as e:
                import logging

                logging.getLogger(__name__).error(
                    "alert_channel_failed",
                    extra={"channel": type(channel).__name__, "error": str(e)},
                )


def build_alert_router() -> AlertRouter:
    """An ``AlertRouter`` with the channels enabled by the environment.

    Slack is registered only when ``SLACK_WEBHOOK_URL`` is set: instantiating
    ``SlackChannel`` without one raises ``KeyError``, which would take a service
    down at import time.
    """
    router = AlertRouter()
    if os.environ.get("SLACK_WEBHOOK_URL"):
        from ace.alerts.channels.slack import SlackChannel

        router.register(SlackChannel())
    return router
