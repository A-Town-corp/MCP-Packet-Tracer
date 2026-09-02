"""Offline behavior tests for capabilities adapted from cisco-pt-mcp."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from urllib.request import Request

import pytest
from mcp.server.fastmcp import FastMCP

from packet_tracer_mcp.adapters.mcp import tool_registry


class _FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@dataclass
class _FakeBridgeHttp:
    results: list[str] = field(default_factory=list)
    queued_commands: list[str] = field(default_factory=list)

    def queue_result(self, payload: dict[str, object]) -> None:
        self.results.append(json.dumps(payload))

    def urlopen(
        self,
        request: str | Request,
        timeout: float = 0,
    ) -> _FakeResponse:
        del timeout
        url = request.full_url if isinstance(request, Request) else request

        if url.endswith("/ping"):
            return _FakeResponse(200, "pong")
        if url.endswith("/status"):
            return _FakeResponse(200, '{"connected": true, "last_poll_ago": 0.1}')
        if url.endswith("/drain"):
            return _FakeResponse(200, '{"drained": 0}')
        if isinstance(request, Request) and url.endswith("/queue"):
            body = request.data.decode("utf-8") if request.data else ""
            self.queued_commands.append(body)
            return _FakeResponse(200, "queued")
        if "/result?" in url:
            if self.results:
                return _FakeResponse(200, self.results.pop(0))
            return _FakeResponse(204, "")

        raise AssertionError(f"unexpected bridge request: {url}")


@pytest.fixture
def live_tools(monkeypatch: pytest.MonkeyPatch) -> tuple[FastMCP, _FakeBridgeHttp]:
    bridge = _FakeBridgeHttp()
    monkeypatch.setattr(tool_registry.urllib.request, "urlopen", bridge.urlopen)
    mcp = FastMCP("live-capability-test")
    tool_registry.register_tools(mcp)
    return mcp, bridge


def _call_text(mcp: FastMCP, name: str, arguments: dict[str, object]) -> str:
    content, _structured = asyncio.run(mcp.call_tool(name, arguments))
    assert len(content) == 1
    return content[0].text


def test_add_device_uses_catalog_type_and_escapes_name(live_tools):
    mcp, bridge = live_tools
    bridge.queue_result({"success": True, "name": 'R"1', "model": "2911"})

    result = json.loads(_call_text(
        mcp,
        "pt_add_device",
        {"device_name": 'R"1', "model": "2911", "x": 120, "y": 240},
    ))

    assert result["success"] is True
    assert 'ptAddDevice("R\\\"1",0,"2911",120,240)' in bridge.queued_commands[-1]


def test_add_device_rejects_unknown_model_without_queueing(live_tools):
    mcp, bridge = live_tools

    result = json.loads(_call_text(
        mcp,
        "pt_add_device",
        {"device_name": "R1", "model": "imaginary-router", "x": 0, "y": 0},
    ))

    assert result == {
        "success": False,
        "error": "Unknown device model: imaginary-router. Call pt_list_devices for valid models.",
    }
    assert bridge.queued_commands == []


def test_add_link_uses_target_cable_enum(live_tools):
    mcp, bridge = live_tools
    bridge.queue_result({"success": True})

    result = json.loads(_call_text(
        mcp,
        "pt_add_link",
        {
            "device_a": "R1",
            "port_a": "GigabitEthernet0/0",
            "device_b": "SW1",
            "port_b": "GigabitEthernet0/1",
            "cable": "straight",
        },
    ))

    assert result["success"] is True
    assert (
        'ptAddLink("R1","GigabitEthernet0/0","SW1",'
        '"GigabitEthernet0/1",8100)'
    ) in bridge.queued_commands[-1]


def test_add_link_rejects_unknown_cable_without_queueing(live_tools):
    mcp, bridge = live_tools

    result = json.loads(_call_text(
        mcp,
        "pt_add_link",
        {
            "device_a": "R1",
            "port_a": "GigabitEthernet0/0",
            "device_b": "SW1",
            "port_b": "GigabitEthernet0/1",
            "cable": "quantum",
        },
    ))

    assert result["success"] is False
    assert "Unknown cable type: quantum" in result["error"]
    assert bridge.queued_commands == []


@pytest.mark.parametrize(
    ("tool_name", "arguments", "command"),
    [
        ("pt_get_network", {}, "ptGetNetwork()"),
        ("pt_get_device_info", {"device_name": "R1"}, 'ptGetDeviceInfo("R1")'),
        (
            "pt_set_device_power",
            {"device_name": "R1", "power": False},
            'ptSetDevicePower("R1",false)',
        ),
        (
            "pt_set_simulation_mode",
            {"simulation": True},
            "ptSetSimulationMode(true)",
        ),
        ("pt_get_simulation_status", {}, "ptGetSimulationStatus()"),
        (
            "pt_step_simulation",
            {"direction": "forward", "steps": 3},
            'ptStepSimulation("forward",3)',
        ),
        (
            "pt_send_pdu",
            {"source_device": "PC1", "destination_device": "PC2"},
            'ptSendPdu("PC1","PC2")',
        ),
        (
            "pt_get_pdu_results",
            {"traffic_types": ["icmp", "Arp"]},
            'ptGetPduResults(["ICMP", "ARP"])',
        ),
        (
            "pt_get_command_log",
            {"device_name": "R1", "limit": 25},
            'ptGetCommandLog("R1",25)',
        ),
    ],
)
def test_live_capability_forwards_structured_json(
    live_tools,
    tool_name: str,
    arguments: dict[str, object],
    command: str,
):
    mcp, bridge = live_tools
    bridge.queue_result({"success": True, "result": {"marker": tool_name}})

    result = json.loads(_call_text(mcp, tool_name, arguments))

    assert result == {"success": True, "result": {"marker": tool_name}}
    assert command in bridge.queued_commands[-1]


def test_runtime_patch_contains_native_packet_tracer_apis(live_tools):
    mcp, bridge = live_tools
    bridge.queue_result({"success": True, "result": {"mode": "realtime"}})

    _call_text(mcp, "pt_get_simulation_status", {})

    runtime_patch = bridge.queued_commands[0]
    assert "ipc.simulation()" in runtime_patch
    assert "getUserCreatedPDU" in runtime_patch
    assert "getFrameInstanceAt" in runtime_patch
    assert "ipc.commandLog()" in runtime_patch
    assert "getConnectionType" in runtime_patch
    assert "setPower" in runtime_patch


@pytest.mark.parametrize(
    ("tool_name", "arguments", "error_fragment"),
    [
        (
            "pt_step_simulation",
            {"direction": "sideways", "steps": 1},
            "direction must be one of: forward, backward, reset",
        ),
        (
            "pt_step_simulation",
            {"direction": "forward", "steps": 101},
            "steps must be between 1 and 100",
        ),
        (
            "pt_get_pdu_results",
            {"traffic_types": ["ICMP", "NOT_A_PROTOCOL"]},
            "Unsupported traffic type: NOT_A_PROTOCOL",
        ),
        (
            "pt_get_command_log",
            {"device_name": "", "limit": 0},
            "limit must be between 1 and 500",
        ),
    ],
)
def test_invalid_live_arguments_are_rejected_before_queueing(
    live_tools,
    tool_name: str,
    arguments: dict[str, object],
    error_fragment: str,
):
    mcp, bridge = live_tools

    result = json.loads(_call_text(mcp, tool_name, arguments))

    assert result["success"] is False
    assert error_fragment in result["error"]
    assert bridge.queued_commands == []
