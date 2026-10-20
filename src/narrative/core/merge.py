"""Pure three-way merge of story JSON; unresolved choices never establish canon.

Stable node/edge IDs are JSON-pointer map keys during merge. Ordinary ordered
arrays remain atomic. The caller owns graph/state validation and authorization.
"""

from copy import deepcopy
from math import isfinite


_MISSING = object()
_RECORD_COLLECTIONS = {"nodes", "edges"}
_CHOICES = {"base", "ours", "theirs"}


def _copy(value):
    return _MISSING if value is _MISSING else deepcopy(value)


def _same(left, right):
    """JSON equality, retaining the distinction between booleans and numbers."""
    if left is _MISSING or right is _MISSING:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if isinstance(left, (dict, list)) or isinstance(right, (dict, list)):
        return False
    return left == right


def _validate_json(value):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_json(item)
        return
    raise ValueError("merge inputs must contain finite JSON values and string object keys")


def _prepare(document):
    if not isinstance(document, dict):
        raise ValueError("merge inputs must be Project JSON objects")
    _validate_json(document)
    result = deepcopy(document)
    result.pop("version", None)
    for collection in sorted(_RECORD_COLLECTIONS):
        records = result.get(collection, [])
        if not isinstance(records, list):
            raise ValueError(f"{collection} must be an array of records with stable IDs")
        indexed = {}
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
                raise ValueError(f"each {collection} record requires a nonempty string ID")
            if record["id"] in indexed:
                raise ValueError(f"duplicate {collection} ID: {record['id']}")
            version = record.get("version", 1)
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise ValueError("node and edge versions must be positive integers")
            indexed[record["id"]] = record
        result[collection] = indexed
    return result


def _pointer(path):
    return "".join("/" + part.replace("~", "~0").replace("/", "~1") for part in path)


def _conflict(base, ours, theirs, path, conflicts, resolutions, reason=None):
    pointer = _pointer(path)
    values = {"base": base, "ours": ours, "theirs": theirs}
    if pointer in resolutions:
        return _copy(values[resolutions[pointer]])
    if reason is None:
        if base is _MISSING:
            reason = "add_add"
        elif ours is _MISSING:
            reason = "delete_modify"
        elif theirs is _MISSING:
            reason = "modify_delete"
        elif any(isinstance(value, list) for value in values.values()):
            reason = "ordered_list_changes"
        else:
            reason = "concurrent_changes"
    conflict = {"path": pointer, "reason": reason}
    for name, value in values.items():
        conflict[name] = None if value is _MISSING else deepcopy(value)
        conflict[f"{name}_exists"] = value is not _MISSING
    conflicts.append(conflict)
    # Missing ours deliberately omits this key/record in the tentative document.
    return _copy(ours)


def _without_version(record):
    if record is _MISSING:
        return _MISSING
    return {key: value for key, value in record.items() if key != "version"}


def _merge_record(base, ours, theirs, path, conflicts, resolutions):
    b, o, t = (_without_version(record) for record in (base, ours, theirs))
    if _same(o, t):
        merged = _copy(o)
    elif _same(o, b):
        merged = _copy(t)
    elif _same(t, b):
        merged = _copy(o)
    elif base is _MISSING or ours is _MISSING or theirs is _MISSING:
        # Independently created entities that collide on ID must not be silently
        # combined, and deletion must stay distinct from a present empty object.
        selected = _conflict(base, ours, theirs, path, conflicts, resolutions)
        merged = _without_version(selected)
    else:
        merged = _merge_mapping(b, o, t, path, conflicts, resolutions)
    if merged is _MISSING:
        return _MISSING
    versions = [record.get("version", 1) for record in (base, ours, theirs) if record is not _MISSING]
    # A selected side keeps its counter where possible. Counter-only differences
    # never conflict or cause regression; a genuinely composite record advances.
    composite = not _same(merged, o) and not _same(merged, t)
    merged["version"] = max(versions, default=1) + int(composite)
    return merged


def _merge_mapping(base, ours, theirs, path, conflicts, resolutions):
    result = {}
    base_mapping = {} if base is _MISSING else base
    for key in sorted(base_mapping.keys() | ours.keys() | theirs.keys()):
        value = _merge(base_mapping.get(key, _MISSING), ours.get(key, _MISSING), theirs.get(key, _MISSING), (*path, key), conflicts, resolutions)
        if value is not _MISSING:
            result[key] = value
    return result


def _merge(base, ours, theirs, path, conflicts, resolutions):
    if len(path) == 1 and path[0] in _RECORD_COLLECTIONS:
        # Do not short-circuit whole collections: every selected record still
        # needs its derived counter normalized against all three inputs.
        return _merge_mapping(base, ours, theirs, path, conflicts, resolutions)
    if len(path) == 2 and path[0] in _RECORD_COLLECTIONS:
        return _merge_record(base, ours, theirs, path, conflicts, resolutions)
    if _same(ours, theirs):
        return _copy(ours)
    if _same(ours, base):
        return _copy(theirs)
    if _same(theirs, base):
        return _copy(ours)
    if isinstance(ours, dict) and isinstance(theirs, dict) and (isinstance(base, dict) or base is _MISSING):
        return _merge_mapping(base, ours, theirs, path, conflicts, resolutions)
    return _conflict(base, ours, theirs, path, conflicts, resolutions)


def _run(base, ours, theirs, resolutions):
    conflicts = []
    # Always visit the top-level maps so version-only record differences pass
    # through the record-counter policy rather than a whole-document shortcut.
    document = _merge_mapping(base, ours, theirs, (), conflicts, resolutions)
    for collection in sorted(_RECORD_COLLECTIONS):
        records = document.get(collection, {})
        document[collection] = [records[key] for key in sorted(records)]
    return {"document": document, "conflicts": conflicts}


def merge_documents(base, ours, theirs, resolutions=None):
    """Merge Project JSON without mutating inputs or validating narrative truth.

    Conflict paths use RFC 6901 escaping and stable record IDs, for example
    ``/nodes/SCENE_1/attributes/motivation``. Choices may name only actual
    conflicts and must be exactly ``ours``, ``theirs`` or ``base``. Unresolved
    paths retain ours as a tentative placeholder; missing ours omits the field.

    Node/Edge counters do not participate in content conflicts. A result with
    contributions from both changed records advances the maximum counter by
    one; selected content keeps the maximum known counter. Project.version is
    omitted because the persistence layer supplies the revision identity.
    """
    prepared = [_prepare(document) for document in (base, ours, theirs)]
    if resolutions is None:
        resolutions = {}
    if not isinstance(resolutions, dict) or not all(isinstance(path, str) for path in resolutions):
        raise ValueError("resolutions must map exact conflict JSON pointers to choices")
    if any(not isinstance(choice, str) or choice not in _CHOICES for choice in resolutions.values()):
        raise ValueError("conflict choices must be ours, theirs or base")
    initial = _run(*prepared, {})
    known_paths = {conflict["path"] for conflict in initial["conflicts"]}
    unknown = sorted(set(resolutions) - known_paths)
    if unknown:
        raise ValueError("unknown conflict resolution path(s): " + ", ".join(unknown))
    return _run(*prepared, resolutions) if resolutions else initial
