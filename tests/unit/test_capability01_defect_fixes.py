"""Service validation and legacy response regressions from the recorded live failures."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from mcp_service.agents.modeling import ModelingAgent
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import TOOL_DEFINITIONS, validate_tool_input
from blender_addon.universal_mcp.bridge.curve_contract import legacy_request


def test_apply_modifier_optional_type_service_validation():
    args = dict(name='Owned', modifier_name='Bevel', expected_snapshot_id='sha256:' + 'a' * 64)
    validate_tool_input('apply_modifier', args, trusted_approval=True)
    assert ModelingAgent().validate_task_input('apply_modifier', args)[0]
    for change in ({'modifier_type': 'INVALID'}, {'expected_snapshot_id': 'bad'}):
        assert not ModelingAgent().validate_task_input('apply_modifier', dict(args, **change))[0]


def test_all_advertised_legacy_curve_enums_validate():
    for kind in TOOL_DEFINITIONS['create_curve_or_text']['input_schema']['properties']['curve_type']['enum']:
        clean, returned_kind, transforms = legacy_request(dict(name='Curve', curve_type=kind, location=[15, 20, 0]))
        assert returned_kind == kind
        assert transforms['location'] == [15, 20, 0]
        if kind in ('NURBS_CURVE', 'PATH'):
            assert clean['splines'][0]['type'] == 'NURBS'


def test_recorded_landmark_nested_failure_becomes_failed_agent_result():
    events = json.loads((Path(__file__).resolve().parents[2] / 'docs/verification/live_testing/capability_01_modeling_sculpting/events_final.json').read_text())
    event = next(e for e in events if e['tool'] == 'guide_mesh_landmarks')
    recorded = json.loads(event['response']['content'][0]['text'])
    assert recorded['status'] == 'success' and recorded['result']['status'] == 'ERROR'
    executor = SimpleNamespace(execute_tool=Mock(return_value=BridgeResponse.success(recorded['result'])))
    agent = ModelingAgent()
    capability = next(c.capability_id for c in agent.manifest.capabilities if 'guide_mesh_landmarks' in c.supported_task_types)
    result = agent.execute_task(AgentTask(task_id='recorded-rejection', required_capability=capability, task_type='guide_mesh_landmarks', input_params=event['args']), executor, trusted_approval=True)
    assert result.status == TaskStatus.FAILED
    assert 'Guidance step failed acceptance criteria' in str(result.errors)
