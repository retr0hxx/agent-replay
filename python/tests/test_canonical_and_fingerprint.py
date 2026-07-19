from agentreplay.canonical import canonical_json
from agentreplay.fingerprint import fingerprint


def test_canonical_is_key_sorted_and_compact():
    obj = {"b": 2, "a": [3, {"z": 1, "y": 2}]}
    assert canonical_json(obj) == '{"a":[3,{"y":2,"z":1}],"b":2}'


def test_canonical_unicode_verbatim():
    assert canonical_json({"k": "日本語"}) == '{"k":"日本語"}'


def test_fingerprint_deterministic_and_reordering_insensitive():
    a = fingerprint("POST", "api.anthropic.com", "/v1/messages", {"model": "m", "messages": []})
    b = fingerprint("post", "API.Anthropic.com", "/v1/messages", {"messages": [], "model": "m"})
    assert a == b
    assert a.startswith("sha256:")


def test_fingerprint_norm_differs_from_exact_when_preset_applies():
    body = {"trace_id": "12345678-1234-4abc-8def-1234567890ab", "hello": "world"}
    exact = fingerprint("POST", "h", "/p", body)
    norm = fingerprint("POST", "h", "/p", body, presets=["uuids"])
    assert exact != norm
