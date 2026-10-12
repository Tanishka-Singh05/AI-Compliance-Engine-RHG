import json
from unittest.mock import AsyncMock, MagicMock, patch


def _sqs_event() -> dict:
    return {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_type": "gate.decision",
                        "pipeline_id": "pipe-001",
                        "repo": "org/svc",
                        "environment": "production",
                        "severity": "HIGH",
                        "findings_count": 2,
                        "blocking_rules": ["CIS-K8S-5.2.1"],
                        "decision": "BLOCK",
                        "report_url": "http://dashboard/d/ace-rhg-overview",
                        "mutation_count": 0,
                        "escalation_reason": "",
                    }
                )
            }
        ]
    }


def test_dispatcher_fans_out_sqs_record():
    import infra.aws_lambda.handlers.alert_dispatcher_handler as mod

    router = MagicMock()
    router.dispatch = AsyncMock()
    mod._router = None
    with patch.object(mod, "build_alert_router", return_value=router):
        result = mod.handler(_sqs_event(), MagicMock())

    assert result["statusCode"] == 200
    router.dispatch.assert_awaited_once()
    payload = router.dispatch.await_args.args[0]
    assert payload.event_type == "gate.decision"
    assert payload.decision == "BLOCK"
    assert payload.severity.value == "HIGH"


def test_dispatcher_handles_empty_event():
    import infra.aws_lambda.handlers.alert_dispatcher_handler as mod

    mod._router = None
    with patch.object(mod, "build_alert_router", return_value=MagicMock()):
        assert mod.handler({"Records": []}, MagicMock())["statusCode"] == 200
