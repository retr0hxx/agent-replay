from agentreplay.paths import iter_targets
from agentreplay.redaction import apply_redaction, strip_auth_headers
from agentreplay.normalization import normalize


def test_iter_targets_dotted_and_wildcard():
    obj = {"a": {"b": [{"c": 1}, {"c": 2}]}}
    hits = list(iter_targets(obj, "a.b[*].c"))
    assert len(hits) == 2
    for container, key in hits:
        container[key] = 0
    assert obj == {"a": {"b": [{"c": 0}, {"c": 0}]}}


def test_redaction_replaces_scalar():
    body = {"api_key": "secret", "messages": [{"content": "hi"}]}
    out = apply_redaction(body, [{"path": "api_key", "replace": "***"}])
    assert out["api_key"] == "***"
    assert body["api_key"] == "secret"  # deep-copied


def test_strip_auth_headers_case_insensitive():
    h = {"Authorization": "Bearer x", "X-Api-Key": "abc", "User-Agent": "test"}
    out = strip_auth_headers(h)
    assert out == {"User-Agent": "test"}


def test_normalize_presets_replace_with_sentinel():
    body = {"created_at": "2026-01-01T00:00:00Z", "id": "12345678-1234-4abc-8def-1234567890ab"}
    out = normalize(body, presets=["timestamps", "uuids"])
    assert out["created_at"] == "<NORMALIZED>"
    assert out["id"] == "<NORMALIZED>"


def test_normalize_ignore_paths_removes_dict_key():
    body = {"a": {"trace": "x", "keep": 1}}
    out = normalize(body, ignore_paths=["a.trace"])
    assert out == {"a": {"keep": 1}}
