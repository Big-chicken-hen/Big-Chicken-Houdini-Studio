"""Compact observation payloads without changing receipts or skipping page rows."""
from __future__ import annotations

import copy

from .common import encoded

BUDGET = 12 * 1024
PAGED = {"nodes", "types", "parameters", "members"}
RECORDS = PAGED | {"connections", "elements", "categories", "checks"}
# Only display prose may become a prefix. All other strings can be addresses,
# parameter values or identifiers used by a later call, including array items.
PROSE = {"help", "documentation", "description", "label", "message", "reason", "text", "errors", "warnings"}


def _size(value):
    return len(encoded(value).encode("utf-8"))


def _page_after_trim(record, key, count):
    page = record.get("parameter_page") if key == "parameters" and "parameter_page" in record else record
    if key in PAGED and "offset" in page and "total" in page:
        end = page["offset"] + count
        page.update(next_offset=end if end < page["total"] else None, truncated=end < page["total"])
    elif "total" in page and key in {"nodes", "categories"}:
        page["truncated"] = page["total"] > count
    else:
        record[key + "_truncated"] = True


def _shrink(record, rows, chars):
    if not isinstance(record, dict):
        return
    for key, value in list(record.items()):
        if isinstance(value, str) and key in PROSE and len(value) > chars:
            record[key] = value[:chars]
            record[key + "_truncated"] = True
            if key == "text" and "total_characters" in record and "offset" in record:
                end = record["offset"] + len(record[key])
                record.update(next_offset=end if end < record["total_characters"] else None,
                              truncated=end < record["total_characters"])
        elif isinstance(value, list):
            if key in RECORDS and len(value) > rows:
                if key == "checks":
                    value = sorted(value, key=lambda item: isinstance(item, dict) and item.get("passed") is True)
                record[key] = value[:rows]
                if key not in PAGED or "total" not in record and "parameter_page" not in record:
                    record.setdefault(key + "_total", len(value))
                _page_after_trim(record, key, rows)
            elif key not in {"views", "requests"} and len(value) > 16:
                record[key] = value[:16]
                record[key + "_total"] = len(value)
                record[key + "_truncated"] = True
            for index, item in enumerate(record[key]):
                if isinstance(item, str) and key in PROSE and len(item) > chars:
                    record[key][index] = {"text": item[:chars], "truncated": True}
                else:
                    _shrink(item, rows, chars)
        elif isinstance(value, dict):
            if key == "values" and len(value) > rows:
                record[key] = dict(list(value.items())[:rows])
                record[key + "_total"] = len(value)
                record[key + "_truncated"] = True
                value = record[key]
            _shrink(value, rows, chars)


def _stub(item):
    """Keep every query identity/status, with explicit omitted records, never fake []."""
    result = {key: value for key, value in item.items() if not isinstance(value, (dict, list))}
    for key in ("error", "flags", "editability", "cook", "network", "filters"):
        if key in item:
            result[key] = item[key]
    for key in PAGED:
        if key in item:
            result[key] = None
            result[key + "_summary_omitted"] = True
            if key == "parameters" and "parameter_page" in item:
                result["parameter_page"] = dict(item["parameter_page"])
            _page_after_trim(result, key, 0)
    result["summary_omitted_fields"] = [key for key in item if key not in result or result[key] is None and item[key] is not None]
    return result


def observation_summary(kind, detail, *, receipt=True):
    # The caller must sanitize the original detail first, including credentials
    # straddling a future truncation boundary. Original detail is never mutated.
    if kind not in {"context", "inspect", "lookup", "execute", "capture"} or _size(detail) <= BUDGET:
        return detail
    result = None
    for rows, chars in ((8, 512), (4, 256), (2, 128), (1, 64)):
        result = copy.deepcopy(detail)
        _shrink(result, rows, chars)
        result["summary"] = {"truncated": True, "budget_bytes": BUDGET,
            "continuation": "hia_operation detail using the enclosing operation_id" if receipt else
                            "Repeat hia_lookup with the same symbol, members=true and offset=next_offset; query an individual member for full metadata"}
        if receipt:
            result["detail_available"] = True
        if _size(result) <= BUDGET:
            return result
    # Very large batches still retain every item. Free room from the largest
    # row payloads, leaving any next cursor at the first row not actually sent.
    if "value" in result and _size(result["value"]) > BUDGET // 2:
        result["value"] = {"summary_omitted": True, "reason": "Read the original operation detail for script return data"}
    items = result.get("views", result.get("requests", result.get("observe_after", {}).get("views", [])))
    for index in sorted(range(len(items)), key=lambda i: _size(items[i]), reverse=True):
        items[index] = _stub(items[index])
        if _size(result) <= BUDGET:
            return result
    return result  # Approximate budget; never discard identities or execution facts.


def capture_manifest_summary(detail):
    """Keep the existing 16 KiB manifest reader valid; full facts stay in receipt."""
    result = observation_summary("capture", detail)
    if _size(result) <= BUDGET:
        return result
    # Very long target addresses belong to the original operation detail. Do not
    # shorten them into unusable addresses or enlarge the artifact protocol.
    result = {key: detail.get(key) for key in ("capture_api", "purpose", "requested_frame", "actual_frame",
        "frame_before", "restored_frame", "requested_resolution", "actual_resolution")}
    result["capture_error_code"] = (detail.get("capture_error") or {}).get("code")
    result["restore_error_phases"] = [error.get("phase") for error in detail.get("restore_errors", [])]
    result["metadata_in_operation_detail"] = True
    return result
