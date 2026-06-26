# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock

from generic_ml_cache_core.application.domain.model.gateway.forwarded_response import (
    ForwardedResponse,
)
from generic_ml_cache_core.application.domain.model.gateway.gateway_request import GatewayRequest
from generic_ml_cache_core.application.port.inbound.run_ml_gateway_command import (
    RunMlGatewayCommand,
)
from generic_ml_cache_core.application.usecase.run_ml_gateway_service import RunMlGatewayService


def _make_request(model="claude-3-5-sonnet-20241022"):
    return GatewayRequest(
        model=model,
        messages=[{"role": "user", "content": "hello"}],
        system=None,
        max_tokens=1024,
    )


def _make_command(request=None, session_id="sess-1"):
    return RunMlGatewayCommand(
        gateway_request=request or _make_request(),
        api_token="sk-test",
        target_url="https://api.anthropic.com/v1/messages",
        forward_headers={},
        session_id=session_id,
    )


def _make_service(blob_store=None, forward_port=None, repository=None, metrics=None):
    return RunMlGatewayService(
        blob_store=blob_store or MagicMock(),
        gateway_forward_port=forward_port or MagicMock(),
        repository=repository or MagicMock(),
        metrics=metrics or MagicMock(),
    )


_RESPONSE_BODY = b'{"content":[{"text":"hi"}],"usage":{"input_tokens":5,"output_tokens":3}}'


class TestLoadCachedResponse:
    def test_returns_none_when_not_cacheable(self):
        request = MagicMock()
        request.is_cacheable.return_value = False
        svc = _make_service()
        assert svc.load_cached_response(_make_command(request=request)) is None

    def test_returns_none_on_miss(self):
        blob = MagicMock()
        blob.get.return_value = None
        svc = _make_service(blob_store=blob)
        assert svc.load_cached_response(_make_command()) is None

    def test_returns_response_on_hit(self):
        blob = MagicMock()
        blob.get.return_value = _RESPONSE_BODY
        svc = _make_service(blob_store=blob)
        resp = svc.load_cached_response(_make_command())
        assert resp is not None
        assert resp.cache_hit is True
        assert resp.status_code == 200
        assert resp.response_body_bytes == _RESPONSE_BODY

    def test_records_hit_metric(self):
        blob = MagicMock()
        blob.get.return_value = _RESPONSE_BODY
        metrics = MagicMock()
        svc = _make_service(blob_store=blob, metrics=metrics)
        svc.load_cached_response(_make_command())
        metrics.record_event.assert_called_once()
        call_kwargs = metrics.record_event.call_args[1]
        assert call_kwargs["session_id"] == "sess-1"


class TestRecordForwardedResponse:
    def test_stores_and_records_on_success(self):
        blob = MagicMock()
        repo = MagicMock()
        metrics = MagicMock()
        svc = _make_service(blob_store=blob, repository=repo, metrics=metrics)
        forwarded = ForwardedResponse(body_bytes=_RESPONSE_BODY, status_code=200)
        resp = svc.record_forwarded_response(_make_command(), forwarded)
        assert resp.cache_hit is False
        assert resp.status_code == 200
        assert blob.put.called
        assert repo.save.called
        assert metrics.record_event.called

    def test_does_not_store_on_error(self):
        blob = MagicMock()
        repo = MagicMock()
        metrics = MagicMock()
        svc = _make_service(blob_store=blob, repository=repo, metrics=metrics)
        forwarded = ForwardedResponse(body_bytes=b'{"error":"bad"}', status_code=500)
        resp = svc.record_forwarded_response(_make_command(), forwarded)
        assert resp.status_code == 500
        blob.put.assert_not_called()
        repo.save.assert_not_called()

    def test_returns_non_cached_response(self):
        blob = MagicMock()
        blob.get.return_value = None
        forwarded = ForwardedResponse(body_bytes=_RESPONSE_BODY, status_code=200)
        svc = _make_service(blob_store=blob)
        resp = svc.record_forwarded_response(_make_command(), forwarded)
        assert resp.cache_hit is False


class TestExecute:
    def test_returns_cached_on_hit(self):
        blob = MagicMock()
        blob.get.return_value = _RESPONSE_BODY
        forward_port = MagicMock()
        svc = _make_service(blob_store=blob, forward_port=forward_port)
        resp = svc.execute(_make_command())
        assert resp.cache_hit is True
        forward_port.forward.assert_not_called()

    def test_forwards_on_miss(self):
        blob = MagicMock()
        blob.get.return_value = None
        forward_port = MagicMock()
        forward_port.forward.return_value = ForwardedResponse(
            body_bytes=_RESPONSE_BODY, status_code=200
        )
        svc = _make_service(blob_store=blob, forward_port=forward_port)
        resp = svc.execute(_make_command())
        assert resp.cache_hit is False
        forward_port.forward.assert_called_once()
