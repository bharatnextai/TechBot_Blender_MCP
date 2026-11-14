"""Test-only post-commit reporting fault; no approval or routing bypass."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mcp_service import app
from mcp_service.execution.blender_executor import BlenderExecutor
args=app.parse_args();root=Path(os.environ['UMCP_LOCAL_TEST_ROOT']).resolve(strict=True)
assert root.name.startswith('umcp-modeling-once-') and args.bridge_port!=9877
original=BlenderExecutor.execute_tool;count=[0]

def injected(self,tool_name,arguments=None,trusted_approval=None):
    if tool_name=='configure_modeling_object':
        count[0]+=1;(root/'invocations.json').write_text(json.dumps({'count':count[0]}))
    response=original(self,tool_name,arguments,trusted_approval=trusted_approval)
    if tool_name=='configure_modeling_object' and trusted_approval is True and response.is_success:raise TypeError('TEST_POST_COMMIT_TYPEERROR: mutation outcome must be inspected')
    return response

BlenderExecutor.execute_tool=injected
app.main()
