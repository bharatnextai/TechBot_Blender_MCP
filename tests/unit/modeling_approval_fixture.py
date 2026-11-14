"""Trusted unittest-host approval; never imported by the service or add-on."""
def approved(tool,params):
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    params={k:v for k,v in params.items() if k not in ("trusted_approval","_trusted_test_override")}
    registry=get_approval_registry();request=registry.create_request(tool,params)
    ok,token=registry.resolve_request(request.request_id,"approved")
    assert ok
    return {**params,"request_id":request.request_id,"approval_token":token}
