"""Presentation facts from native tool items and existing runtime receipts."""
from __future__ import annotations

import json


def is_tool(item):
    return item.get("type") not in {"userMessage", "agentMessage", "reasoning", "plan", "contextCompaction", "imageView"}


def activity_segments(ordered):
    """Keep native order: an intervening message or another turn ends a segment."""
    segments, active = {}, None
    for key, item in ordered:
        if not is_tool(item):
            active = None
            continue
        if active is None or active.turn != key.turn:
            active = key
            segments[active] = []
        segments[active].append(key)
    return segments


def tool_facts(item):
    payload = item.get("result") or {}
    values = []
    if isinstance(payload, dict):
        for content in payload.get("content", []):
            if content.get("type") == "text":
                try:
                    value = json.loads(content.get("text", ""))
                except (ValueError, TypeError):
                    continue
                if isinstance(value, dict):
                    values.append(value)
    receipt = next((v for v in values if v.get("operation_id")), {})
    result = receipt.get("result") or {}
    errors = [v.get("error") for v in values if v.get("error")]
    if item.get("error"):
        errors.append(item["error"])
    state = receipt.get("state")
    mutation = receipt.get("mutation_outcome")
    warning = ""
    if state == "unknown" or receipt.get("receipt_confirmed") is False or mutation == "unknown" and state in {"finished", "failed"}:
        warning = "执行结果未确认"
    elif mutation == "partial":
        warning = "操作留下了部分修改"
    elif receipt.get("checks_outcome") == "failed":
        warning = "操作检查发现问题"
    elif state in {"failed", "rejected"} or errors or item.get("status") == "failed" or isinstance(payload, dict) and payload.get("isError"):
        warning = "操作失败" if state != "rejected" else "操作未执行"
    elif state == "cancelled":
        warning = "操作已取消；取消不会回滚已经完成的修改"
    elif isinstance(result, dict) and (result.get("restore_errors") or result.get("capture_error") or result.get("status") == "partial"):
        warning = "操作结果包含需要查看的问题"
    # Recovery warnings may accompany otherwise successful observation/capture.
    elif isinstance(result, dict) and (result.get("warnings") or (result.get("observe_after") or {}).get("status") == "partial"):
        warning = "操作返回了恢复或观察提示"
    frame = result.get("actual_frame", result.get("frame")) if isinstance(result, dict) else None
    target = (item.get("arguments") or {}).get("target") or {}
    paths = target.get("paths", []) if isinstance(target, dict) else []
    caption = " · ".join([*( ["帧 " + str(frame)] if frame is not None else []),
                          *( ["、".join(str(p).rsplit("/", 1)[-1] for p in paths)] if paths else [])])
    return {"receipt": receipt, "warning": warning, "caption": caption}


def running_operation_text(runtime, receipts, *, stopping=False):
    """Never infer runtime completion or step progress from Codex turn status."""
    active_id = runtime.get("active_operation_id")
    receipt = receipts.get(active_id, {}) if active_id else {}
    if not active_id and not runtime.get("main_thread_busy"):
        return ""
    if stopping or receipt.get("cancel_requested"):
        return "已请求停止，等待当前步骤结束"
    if receipt.get("state") not in {"queued", "running"}:
        return "Houdini 仍在执行，等待当前操作的收据"
    if receipt.get("kind") == "capture":
        return "正在获取视图"
    detail = receipt.get("result") or {}
    steps = receipt.get("steps", detail.get("steps", []))
    active_step = receipt.get("active_step", detail.get("active_step"))
    current = next(((i, step) for i, step in enumerate(steps, 1) if step.get("id") == active_step), None)
    if current:
        index, step = current
        return f"Houdini 正在执行：{step.get('label') or receipt.get('label', '当前操作')}\n阶段 {index} / {len(steps)}"
    return "Houdini 正在执行：" + str(receipt.get("label") or "当前操作")
