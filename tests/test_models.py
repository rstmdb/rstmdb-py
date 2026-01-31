import pytest
from pydantic import ValidationError

from rstmdb.models import (
    ApplyEventResult,
    CreateInstanceResult,
    ErrorCode,
    GetInstanceResult,
    GetMachineResult,
    Operation,
    PutMachineResult,
    Request,
    Response,
    ResponseError,
    StreamEvent,
    UnwatchResult,
    WatchAllResult,
    WatchInstanceResult,
)


class TestOperation:
    """Tests for Operation enum."""

    def test_all_operations_defined(self) -> None:
        """All expected operations are defined."""
        expected = [
            "HELLO",
            "AUTH",
            "PING",
            "BYE",
            "INFO",
            "PUT_MACHINE",
            "GET_MACHINE",
            "LIST_MACHINES",
            "CREATE_INSTANCE",
            "GET_INSTANCE",
            "DELETE_INSTANCE",
            "APPLY_EVENT",
            "BATCH",
            "SNAPSHOT_INSTANCE",
            "WAL_READ",
            "COMPACT",
            "WATCH_INSTANCE",
            "WATCH_ALL",
            "UNWATCH",
        ]
        for op in expected:
            assert hasattr(Operation, op)
            assert Operation[op].value == op

    def test_operation_is_string(self) -> None:
        """Operations serialize as strings."""
        assert Operation.PING == "PING"
        assert Operation.PING.value == "PING"


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_all_error_codes_defined(self) -> None:
        """All expected error codes are defined."""
        expected = [
            # Protocol errors
            "UNSUPPORTED_PROTOCOL",
            "BAD_REQUEST",
            # Auth errors
            "UNAUTHORIZED",
            "AUTH_FAILED",
            # Not found errors
            "NOT_FOUND",
            "MACHINE_NOT_FOUND",
            "INSTANCE_NOT_FOUND",
            # Already exists errors
            "MACHINE_VERSION_EXISTS",
            "INSTANCE_EXISTS",
            # State machine errors
            "INVALID_TRANSITION",
            "GUARD_FAILED",
            "CONFLICT",
            # System errors
            "WAL_IO_ERROR",
            "INTERNAL_ERROR",
            "RATE_LIMITED",
        ]
        for code in expected:
            assert hasattr(ErrorCode, code)


class TestRequest:
    """Tests for Request model."""

    def test_minimal_request(self) -> None:
        """Create request with minimal fields."""
        req = Request(id="1", op=Operation.PING)

        assert req.type == "request"
        assert req.id == "1"
        assert req.op == Operation.PING
        assert req.params == {}

    def test_request_with_params(self) -> None:
        """Create request with params."""
        req = Request(
            id="2",
            op=Operation.CREATE_INSTANCE,
            params={"machine": "order", "version": 1},
        )

        assert req.params == {"machine": "order", "version": 1}

    def test_request_serialization(self) -> None:
        """Request serializes to JSON."""
        req = Request(id="1", op=Operation.PING)
        data = req.model_dump()

        assert data["type"] == "request"
        assert data["id"] == "1"
        assert data["op"] == "PING"

    def test_request_json_roundtrip(self) -> None:
        """Request survives JSON serialization round trip."""
        req = Request(id="1", op=Operation.PING, params={"key": "value"})
        json_str = req.model_dump_json()
        restored = Request.model_validate_json(json_str)

        assert restored.id == req.id
        assert restored.op == req.op
        assert restored.params == req.params


class TestResponse:
    """Tests for Response model."""

    def test_success_response(self) -> None:
        """Parse success response."""
        resp = Response(
            id="1",
            status="ok",
            result={"data": "value"},
        )

        assert resp.type == "response"
        assert resp.id == "1"
        assert resp.status == "ok"
        assert resp.result == {"data": "value"}
        assert resp.error is None

    def test_error_response(self) -> None:
        """Parse error response."""
        resp = Response(
            id="1",
            status="error",
            error=ResponseError(
                code=ErrorCode.NOT_FOUND,
                message="Instance not found",
                retryable=False,
            ),
        )

        assert resp.status == "error"
        assert resp.error is not None
        assert resp.error.code == ErrorCode.NOT_FOUND
        assert resp.error.message == "Instance not found"
        assert resp.error.retryable is False

    def test_response_from_dict(self) -> None:
        """Parse response from dict."""
        data = {
            "type": "response",
            "id": "123",
            "status": "ok",
            "result": {"key": "value"},
        }
        resp = Response.model_validate(data)

        assert resp.id == "123"
        assert resp.result == {"key": "value"}


class TestStreamEvent:
    """Tests for StreamEvent model."""

    def test_full_event(self) -> None:
        """Parse complete stream event."""
        event = StreamEvent(
            subscription_id="sub-1",
            instance_id="inst-1",
            machine="order",
            version=1,
            wal_offset=100,
            from_state="created",
            to_state="paid",
            event="PAY",
            payload={"amount": 99.99},
            ctx={"user_id": "123"},
        )

        assert event.type == "event"
        assert event.subscription_id == "sub-1"
        assert event.instance_id == "inst-1"
        assert event.machine == "order"
        assert event.from_state == "created"
        assert event.to_state == "paid"
        assert event.event == "PAY"
        assert event.payload == {"amount": 99.99}
        assert event.ctx == {"user_id": "123"}

    def test_minimal_event(self) -> None:
        """Parse event with minimal fields."""
        event = StreamEvent(
            subscription_id="sub-1",
            instance_id="inst-1",
            machine="order",
            version=1,
            wal_offset=100,
            from_state="created",
            to_state="paid",
            event="PAY",
        )

        assert event.payload is None
        assert event.ctx is None


class TestResultModels:
    """Tests for result models."""

    def test_put_machine_result(self) -> None:
        """Parse PutMachineResult."""
        result = PutMachineResult(
            machine="order",
            version=1,
            stored_checksum="abc123",
            created=True,
        )

        assert result.machine == "order"
        assert result.version == 1
        assert result.stored_checksum == "abc123"
        assert result.created is True

    def test_get_machine_result(self) -> None:
        """Parse GetMachineResult."""
        result = GetMachineResult(
            definition={"states": ["a", "b"]},
            checksum="def456",
        )

        assert result.definition == {"states": ["a", "b"]}
        assert result.checksum == "def456"

    def test_create_instance_result(self) -> None:
        """Parse CreateInstanceResult."""
        result = CreateInstanceResult(
            instance_id="inst-1",
            state="initial",
            wal_offset=1,
        )

        assert result.instance_id == "inst-1"
        assert result.state == "initial"
        assert result.wal_offset == 1

    def test_get_instance_result(self) -> None:
        """Parse GetInstanceResult."""
        result = GetInstanceResult(
            machine="order",
            version=1,
            state="created",
            ctx={"key": "value"},
            last_wal_offset=10,
        )

        assert result.machine == "order"
        assert result.version == 1
        assert result.state == "created"
        assert result.ctx == {"key": "value"}
        assert result.last_event_id is None
        assert result.last_wal_offset == 10

    def test_apply_event_result(self) -> None:
        """Parse ApplyEventResult."""
        result = ApplyEventResult(
            from_state="created",
            to_state="paid",
            wal_offset=11,
            applied=True,
            ctx={"updated": True},
        )

        assert result.from_state == "created"
        assert result.to_state == "paid"
        assert result.applied is True
        assert result.ctx == {"updated": True}

    def test_watch_instance_result(self) -> None:
        """Parse WatchInstanceResult."""
        result = WatchInstanceResult(
            subscription_id="sub-1",
            instance_id="inst-1",
            current_state="created",
            current_wal_offset=5,
        )

        assert result.subscription_id == "sub-1"
        assert result.instance_id == "inst-1"
        assert result.current_state == "created"

    def test_watch_all_result(self) -> None:
        """Parse WatchAllResult."""
        result = WatchAllResult(
            subscription_id="sub-2",
            wal_offset=100,
        )

        assert result.subscription_id == "sub-2"
        assert result.wal_offset == 100

    def test_unwatch_result(self) -> None:
        """Parse UnwatchResult."""
        result = UnwatchResult(
            subscription_id="sub-1",
            removed=True,
        )

        assert result.subscription_id == "sub-1"
        assert result.removed is True


class TestValidation:
    """Tests for model validation."""

    def test_request_missing_id(self) -> None:
        """Request requires id."""
        with pytest.raises(ValidationError):
            Request(op=Operation.PING)  # type: ignore[call-arg]

    def test_request_missing_op(self) -> None:
        """Request requires op."""
        with pytest.raises(ValidationError):
            Request(id="1")  # type: ignore[call-arg]

    def test_invalid_operation(self) -> None:
        """Invalid operation value raises error."""
        with pytest.raises(ValidationError):
            Request(id="1", op="INVALID_OP")  # type: ignore[arg-type]

    def test_response_error_missing_code(self) -> None:
        """ResponseError requires code."""
        with pytest.raises(ValidationError):
            ResponseError(message="error", retryable=False)  # type: ignore[call-arg]
