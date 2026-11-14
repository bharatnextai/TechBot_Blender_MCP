"""Small stdlib JSON-contract validator for typed modeling, no code evaluation."""
import math

TRANSPORT={"approved","trusted_approval","request_id","approval_token","task_id","session_id","correlation_id"}
NAME={"type":"string","minLength":1,"maxLength":63}
INDEX={"type":"integer","minimum":0,"maximum":1000000}
INDICES={"type":"array","minItems":1,"maxItems":1024,"items":INDEX,"uniqueItems":True}
VECTOR={"type":"array","minItems":3,"maxItems":3,"items":{"type":"number","minimum":-1000000,"maximum":1000000}}
SNAPSHOT={"type":"string","pattern":"^sha256:[0-9a-f]{64}$"}


def check(schema,value,path="params"):
    import re
    kind=schema.get("type")
    if kind is None and isinstance(value,dict) and ("properties" in schema or "required" in schema):kind="object"
    valid={"object":isinstance(value,dict),"array":isinstance(value,(list,tuple)),"string":isinstance(value,str),
           "number":type(value) in (int,float),"integer":type(value) is int,"boolean":type(value) is bool}
    if kind and not valid.get(kind,False):raise ValueError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:raise ValueError(f"{path}: unsupported value")
    if "const" in schema and value!=schema["const"]:raise ValueError(f"{path}: unexpected value")
    if kind in ("number","integer"):
        if not math.isfinite(value) or value<schema.get("minimum",-math.inf) or value>schema.get("maximum",math.inf):raise ValueError(f"{path}: outside finite bounds")
    elif kind=="string":
        if not schema.get("minLength",0)<=len(value)<=schema.get("maxLength",1000000):raise ValueError(f"{path}: string length")
        if "pattern" in schema and not re.fullmatch(schema["pattern"],value):raise ValueError(f"{path}: invalid format")
    elif kind=="array":
        if not schema.get("minItems",0)<=len(value)<=schema.get("maxItems",1000000):raise ValueError(f"{path}: array length")
        if schema.get("uniqueItems"):
            try:unique=len(set(value))==len(value)
            except TypeError:raise ValueError(f"{path}: invalid index values") from None
            if not unique:raise ValueError(f"{path}: duplicate indices")
        for i,item in enumerate(value):check(schema.get("items",{}),item,f"{path}[{i}]")
    elif kind=="object":
        props=schema.get("properties",{})
        if schema.get("additionalProperties") is False and set(value)-set(props):raise ValueError(f"{path}: unknown fields")
        if set(schema.get("required",[]))-set(value):raise ValueError(f"{path}: missing required fields")
        for key,item in value.items():
            if key in props:check(props[key],item,path+"."+key)
    for option in schema.get("allOf",[]):
        try:check(option["if"],value,path)
        except ValueError:
            if "else" in option:check(option["else"],value,path)
        else:check(option.get("then",{}),value,path)


def tool_params(schema,params):
    if not isinstance(params,dict):raise ValueError("Tool parameters must be an object")
    clean={k:v for k,v in params.items() if k not in TRANSPORT}
    check(schema,clean)
    if "name" in clean and (not clean["name"].strip() or clean["name"]!=clean["name"].strip()):raise ValueError("name must be exact and nonblank")
    return clean
