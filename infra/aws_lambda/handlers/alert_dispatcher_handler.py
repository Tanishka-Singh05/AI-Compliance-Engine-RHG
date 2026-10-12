"""SQS-triggered alert dispatcher for the ACE/RHG gate.

The scan/gate pipeline publishes ``gate.decision`` payloads to the
``ace-alerts-<env>.fifo`` queue (see ``ace.alerts.channels.sqs.SQSChannel``).
This handler fans those messages out to the configured alert channels (Slack).

Deployed as the ``ace-dispatcher-<env>`` Lambda using the same image as the
scan function, but with ``ImageConfig.Command`` overridden to
``handlers.alert_dispatcher_handler.handler``.
"""

import asyncio
import json

from ace.alerts.router import AlertPayload, AlertSeverity, build_alert_router

_router = None


def _get_router():
    global _router
    if _router is None:
        _router = build_alert_router()
    return _router


def _payload(record: dict) -> AlertPayload:
    body = json.loads(record["body"])
    return AlertPayload(
        event_type=body["event_type"],
        pipeline_id=body["pipeline_id"],
        repo=body["repo"],
        environment=body["environment"],
        severity=AlertSeverity(body["severity"]),
        findings_count=body["findings_count"],
        blocking_rules=body["blocking_rules"],
        decision=body["decision"],
        report_url=body["report_url"],
        mutation_count=body.get("mutation_count", 0),
        escalation_reason=body.get("escalation_reason", ""),
    )


def handler(event, context):
    router = _get_router()
    for record in event.get("Records", []):
        asyncio.run(router.dispatch(_payload(record)))
    return {"statusCode": 200}
