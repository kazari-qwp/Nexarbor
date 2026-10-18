"""双人协议与延后兑现。

本组件只通过 ctx 访问网络：记录仓、位置、时钟和明确配置的模板端口。
"""

from __future__ import annotations

from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult


class AgreementError(Exception):
    """可由调用者读取的业务错误。"""





def _plain(value):
    return thaw(value)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _lock_order(values):
    return sorted(
        {value for value in values if isinstance(value, str) and value}
    )


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value


async def _local_metadata(ctx):
    try:
        metadata = ctx.metadata()
    except AttributeError:
        return {}
    return await _maybe_await(metadata)


def _entry_id(entry):
    if isinstance(entry, dict):
        for key in ("node_id", "id", "target_node_id"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                return value
        metadata = entry.get("metadata") or entry.get("meta")
        if isinstance(metadata, dict):
            value = metadata.get("node_id")
            if isinstance(value, str) and value:
                return value
        return None
    for key in ("node_id", "id", "target_node_id"):
        value = getattr(entry, key, None)
        if isinstance(value, str) and value:
            return value
    return None


def _entry_metadata(entry):
    if isinstance(entry, dict):
        metadata = entry.get("metadata") or entry.get("meta")
        if metadata is not None:
            return metadata
        return entry
    metadata = getattr(entry, "metadata", None)
    if metadata is not None:
        return metadata
    return entry


def _node_type(metadata):
    if isinstance(metadata, dict):
        return metadata.get("node_type") or metadata.get("type")
    return getattr(metadata, "node_type", None) or getattr(metadata, "type", None)


async def _reachable_nodes(ctx):
    raw = await ctx.network.nodes()
    out = {}
    if raw is None:
        return out
    if isinstance(raw, dict):
        if "nodes" in raw or "items" in raw:
            raw = raw.get("nodes") or raw.get("items") or []
        elif any(key in raw for key in ("node_id", "id", "metadata")):
            raw = [raw]
        else:
            for key, value in raw.items():
                out[str(key)] = _entry_metadata(value)
            return out
    if isinstance(raw, tuple):
        raw = list(raw)
    for entry in raw or []:
        node_id = _entry_id(entry)
        if node_id:
            out[node_id] = _entry_metadata(entry)
    return out


async def _requester_metadata(ctx, requester, cached=None):
    if requester == ctx.node_id:
        return await _local_metadata(ctx)
    if cached is not None and requester in cached:
        return cached[requester]
    return None


async def _node_values(ctx, node_id):
    result = await ctx.network.call(node_id, "records.store", "read", {})
    if result.get("status") != "ok":
        raise AgreementError(result.get("error") or "读取记录失败")
    data = result.get("data") or {}
    return _plain(data.get("values") or {})


async def _node_location(ctx, node_id):
    result = await ctx.network.call(node_id, "place.info", "read", {})
    if result.get("status") != "ok":
        raise AgreementError(result.get("error") or "读取位置失败")
    data = result.get("data") or {}
    if isinstance(data, dict) and "location" in data:
        return data.get("location")
    return None


async def _current_tick(ctx, clock_id):
    result = await ctx.network.call(clock_id, "clock.counter", "read", {})
    if result.get("status") != "ok":
        raise AgreementError(result.get("error") or "读取时钟失败")
    data = result.get("data") or {}
    tick = data.get("tick")
    if not isinstance(tick, int) or isinstance(tick, bool):
        raise AgreementError("时钟未返回有效计数")
    return tick


async def _apply(ctx, node_id, parameters, key):
    payload = {"key": key}
    payload.update(parameters)
    result = await ctx.network.call(node_id, "records.store", "apply", payload)
    if result.get("status") != "ok":
        raise AgreementError(result.get("error") or "更新记录失败")
    data = result.get("data") or {}
    return _plain(data.get("values") or {})


def _rule_by_id(config, rule_id):
    for rule in config.get("rules") or []:
        if rule.get("id") == rule_id:
            return _plain(rule)
    return None


def _agreement_summary(agreement, duplicate=False):
    return {
        "id": agreement.get("id"),
        "rule": agreement.get("rule"),
        "participants": list(agreement.get("participants") or []),
        "approvals": _plain(agreement.get("approvals") or []),
        "created_tick": agreement.get("created_tick"),
        "due_tick": agreement.get("due_tick"),
        "status": agreement.get("status"),
        "completed_tick": agreement.get("completed_tick"),
        "returned_node_ids": _plain(agreement.get("returned_node_ids") or []),
        "duplicate": bool(duplicate),
    }


def _find_agreement(state, agreement_id):
    for agreement in reversed(state.get("agreements") or []):
        if agreement.get("id") == agreement_id:
            return agreement
    return None


def _check_prerequisites(rule, left_values, right_values, left_id, right_id):
    eligible_field = rule.get("eligible_field")
    if eligible_field and not (
        left_values.get(eligible_field) is True
        or right_values.get(eligible_field) is True
    ):
        raise AgreementError("双方均不具备协议所需资格：" + str(eligible_field))
    for field, expected in _plain(rule.get("require_values") or {}).items():
        if left_values.get(field) != expected or right_values.get(field) != expected:
            raise AgreementError("双方尚未满足协议前提：" + str(field))
    for field in _as_list(rule.get("equal_fields")):
        left = left_values.get(field)
        right = right_values.get(field)
        if left in (None, "") or right in (None, "") or left != right:
            raise AgreementError("双方字段必须相同且非空：" + str(field))
    pair_field = rule.get("pair_field")
    if rule.get("require_pair"):
        if not pair_field:
            raise AgreementError("协议规则缺少关系字段")
        if left_values.get(pair_field) != right_id or right_values.get(pair_field) != left_id:
            raise AgreementError("双方尚未与对方建立所需关系")
    if rule.get("forbid_existing_pair"):
        if not pair_field:
            raise AgreementError("协议规则缺少关系字段")
        if left_values.get(pair_field) not in (None, "") or right_values.get(pair_field) not in (None, ""):
            raise AgreementError("双方已有关系，不能重复建立")


def _stable_template_key(ctx, agreement):
    return "%s:%s:%s" % (ctx.module_id, ctx.node_id, agreement.get("id"))


def _fee_key(ctx, agreement, participant, step):
    return "%s:%s:agreements.pair:%s:%s:%s:%s:%s" % (
        ctx.module_id,
        ctx.node_id,
        ctx.requester_id,
        agreement.get("rule"),
        agreement.get("id"),
        participant,
        step,
    )


def _effect_key(ctx, agreement, participant, stage, index):
    return "%s:%s:agreements.pair:effect:%s:%s:%s:%s:%s" % (
        ctx.module_id,
        ctx.node_id,
        agreement.get("id"),
        agreement.get("rule"),
        participant,
        stage,
        index,
    )


def _matches_when(values, when):
    for field, expected in _plain(when or {}).items():
        if values.get(field) != expected:
            return False
    return True


def _check_fulfill_requirements(rule, values):
    for field, expected in _plain(rule.get("fulfill_require_values") or {}).items():
        if values.get(field) != expected:
            raise AgreementError("兑现者尚未满足兑现前提：" + str(field))


async def _apply_effects_for_participant(ctx, rule, agreement, participant, stage):
    effects = _plain(rule.get("participant_effects") or [])
    for index, effect in enumerate(effects):
        if not isinstance(effect, dict):
            continue
        values = await _node_values(ctx, participant)
        if not _matches_when(values, effect.get("when") or {}):
            continue
        settings = _plain(effect.get(stage) or {})
        if not settings:
            continue
        await _apply(
            ctx,
            participant,
            {"set": settings},
            _effect_key(ctx, agreement, participant, stage, index),
        )


async def _apply_effects_stage(ctx, rule, agreement, stage):
    for participant in agreement.get("participants") or []:
        await _apply_effects_for_participant(
            ctx, rule, agreement, participant, stage
        )


async def _complete_records(ctx, rule, agreement, tick):
    pair_field = rule.get("pair_field")
    for participant in agreement.get("participants") or []:
        other = next(
            (item for item in agreement.get("participants") or [] if item != participant),
            None,
        )
        references = []
        if rule.get("forbid_existing_pair") and pair_field and other:
            references.append({"key": pair_field, "node_id": other})
        payload = {}
        if rule.get("set_values"):
            payload["set"] = _plain(rule.get("set_values"))
        if references:
            payload["references"] = references
        if payload:
            await _apply(
                ctx,
                participant,
                payload,
                _fee_key(ctx, agreement, participant, "complete"),
            )
        await _apply_effects_for_participant(
            ctx, rule, agreement, participant, "on_finish"
        )
    agreement["status"] = "completed"
    agreement["completed_tick"] = tick


async def _add_child_references(ctx, agreement, node_ids):
    for participant in agreement.get("participants") or []:
        references = []
        for index, node_id in enumerate(node_ids):
            key = "child" if index == 0 else "child_%d" % (index + 1)
            references.append({"key": key, "node_id": node_id})
        if references:
            await _apply(
                ctx,
                participant,
                {"references": references},
                _fee_key(ctx, agreement, participant, "child"),
            )


def _extract_node_ids(result):
    """从官方模板端口返回中提取真实节点 ID。

    官方 templates:instantiate 返回 {node_ids: {角色: 新节点ID}, duplicate: ...}，
    其中 node_ids 是字典；旧版数组形式也保留支持。只接受非空字符串节点 ID。
    """
    if not isinstance(result, dict):
        return []
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    values = data.get("node_ids")
    if values is None and isinstance(data.get("returned"), dict):
        values = data["returned"].get("node_ids")
    if values is None:
        values = data.get("returned_node_ids")
    if isinstance(values, dict):
        candidates = list(values.values())
    elif isinstance(values, (list, tuple)):
        candidates = list(values)
    elif values is None:
        candidates = []
    else:
        candidates = [values]
    node_ids = []
    for item in candidates:
        node_id = None
        if isinstance(item, str):
            node_id = item
        elif isinstance(item, dict):
            node_id = item.get("node_id")
        if isinstance(node_id, str) and node_id and node_id not in node_ids:
            node_ids.append(node_id)
    return node_ids


def _truncate(state):
    if len(state.get("agreements") or []) > 200:
        state["agreements"] = state["agreements"][-200:]
    if len(state.get("agree_receipts") or []) > 200:
        state["agree_receipts"] = state["agree_receipts"][-200:]


def _local_inspect(ctx, config):
    requester = ctx.requester_id
    rules = []
    for rule in config.get("rules") or []:
        item = _plain(rule)
        rules.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "cost": item.get("cost", 1),
                "fulfill_cost": item.get("fulfill_cost", 0),
                "delay_ticks": item.get("delay_ticks", 0),
                "template": item.get("template"),
                "eligible_field": item.get("eligible_field"),
                "fulfill_require_values": _plain(
                    item.get("fulfill_require_values") or {}
                ),
                "participant_effects": _plain(
                    item.get("participant_effects") or []
                ),
            }
        )
    agreements = []
    for agreement in reversed(ctx.state.get("agreements") or []):
        if requester in (agreement.get("participants") or []):
            agreements.append(_agreement_summary(agreement))
    return {"rules": rules, "agreements": agreements}


async def _source_inspect(ctx, source):
    """调用一个明确配置的来源登记节点，返回它的 inspect 数据副本。"""
    try:
        result = await ctx.network.call(source, ctx.module_id, "inspect", {})
    except Exception as error:
        raise AgreementError(
            "读取来源协议失败：" + str(source) + "：" + str(error)
        )
    if result.get("status") != "ok":
        detail = result.get("error") or "未知错误"
        raise AgreementError("读取来源协议失败：" + str(source) + "：" + str(detail))
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _merge_rules(rules, incoming):
    seen = {
        rule.get("id")
        for rule in rules
        if isinstance(rule, dict) and rule.get("id")
    }
    for rule in incoming or []:
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("id")
        if rule_id and rule_id in seen:
            continue
        rules.append(_plain(rule))
        if rule_id:
            seen.add(rule_id)


async def _inspect(ctx, config):
    """汇总本节点与明确配置的来源登记节点。

    sources 非空时逐个调用来源的 inspect；来源只返回当前请求者可见的协议，
    因此这里无需、也不会扫描全网。来源协议附带 source 字段，规则按 id 合并。
    """
    local = _local_inspect(ctx, config)
    sources = list(config.get("sources") or [])
    if not sources:
        return local

    rules = []
    _merge_rules(rules, local.get("rules") or [])
    agreements = []
    for agreement in local.get("agreements") or []:
        item = _plain(agreement)
        item["source"] = ctx.node_id
        agreements.append(item)

    for source in sources:
        data = await _source_inspect(ctx, source)
        _merge_rules(rules, data.get("rules") or [])
        for agreement in data.get("agreements") or []:
            if not isinstance(agreement, dict):
                continue
            item = _plain(agreement)
            item["source"] = source
            agreements.append(item)
    return {"rules": rules, "agreements": agreements}


async def _agree(ctx, config, parameters):
    requester = ctx.requester_id
    if not requester:
        raise AgreementError("无法确认请求者身份")
    partner = parameters.get("partner")
    rule_id = parameters.get("rule")
    user_key = parameters.get("key")
    rule = _rule_by_id(config, rule_id)
    if rule is None:
        raise AgreementError("协议规则不存在")
    if partner == requester:
        raise AgreementError("不能与自己签订双人协议")

    reachable = await _reachable_nodes(ctx)
    requester_metadata = await _requester_metadata(ctx, requester, reachable)
    if _node_type(requester_metadata) != "agent":
        raise AgreementError(
            "只有真实 Agent 才能同意协议"
        )
    if partner not in reachable:
        raise AgreementError("协议对象不可达")
    if _node_type(reachable.get(partner)) != "agent":
        raise AgreementError("协议对象必须是真实 Agent")

    lock_ids = _lock_order([ctx.node_id, requester, partner, config.get("clock")])
    try:
        async with ctx.network.lock_nodes(lock_ids, timeout=20):
            tick = await _current_tick(ctx, config.get("clock"))
            receipt_key = "%s\x1f%s" % (requester, user_key)
            receipt = next(
                (
                    item
                    for item in ctx.state.get("agree_receipts") or []
                    if item.get("key") == receipt_key
                ),
                None,
            )
            if receipt is not None:
                if receipt.get("partner") != partner or receipt.get("rule") != rule_id:
                    raise AgreementError("幂等键已用于其他协议请求")
                agreement = _find_agreement(ctx.state, receipt.get("agreement_id"))
                if agreement is None:
                    raise AgreementError("原协议记录已不存在")
                return _agreement_summary(agreement, duplicate=True)

            agreement = None
            for item in reversed(ctx.state.get("agreements") or []):
                if (
                    item.get("rule") == rule_id
                    and set(item.get("participants") or []) == {requester, partner}
                    and item.get("status") == "open"
                ):
                    agreement = item
                    break

            address = config.get("address")
            if address:
                requester_location = await _node_location(ctx, requester)
                partner_location = await _node_location(ctx, partner)
                if requester_location != address or partner_location != address:
                    raise AgreementError("双方必须都在协议地点")

            requester_values = await _node_values(ctx, requester)
            partner_values = await _node_values(ctx, partner)
            _check_prerequisites(
                rule, requester_values, partner_values, requester, partner
            )

            if agreement is None:
                agreement = {
                    "id": "agr-%d-%s" % (
                        int(ctx.state.get("sequence", 0)) + 1,
                        str(tick),
                    ),
                    "rule": rule_id,
                    "stable_key": "",
                    "participants": [requester, partner],
                    "approvals": [],
                    "created_tick": tick,
                    "due_tick": None,
                    "status": "open",
                    "completed_tick": None,
                    "pending": None,
                    "returned_node_ids": [],
                }
                ctx.state.setdefault("agreements", []).append(agreement)
                ctx.state["sequence"] = int(ctx.state.get("sequence", 0)) + 1
            else:
                agreement["approvals"] = [
                    item
                    for item in agreement.get("approvals") or []
                    if item.get("tick") == tick
                ]

            already_approved = any(
                item.get("participant") == requester and item.get("tick") == tick
                for item in agreement.get("approvals") or []
            )
            if already_approved:
                receipt = {
                    "key": receipt_key,
                    "requester": requester,
                    "user_key": user_key,
                    "partner": partner,
                    "rule": rule_id,
                    "agreement_id": agreement.get("id"),
                }
                ctx.state.setdefault("agree_receipts", []).append(receipt)
                _truncate(ctx.state)
                return _agreement_summary(agreement, duplicate=True)

            cost = int(rule.get("cost", 1))
            if cost > 0 and requester_values.get("ap", 0) < cost:
                raise AgreementError("行动点不足，无法同意协议")

            if cost > 0:
                await _apply(
                    ctx,
                    requester,
                    {"deltas": {"ap": -cost}},
                    _fee_key(
                        ctx,
                        agreement,
                        requester,
                        "agree-cost:%s:%s" % (user_key, tick),
                    ),
                )

            agreement["approvals"].append(
                {"participant": requester, "tick": tick, "key": user_key}
            )
            approved = {
                item.get("participant")
                for item in agreement.get("approvals") or []
                if item.get("tick") == tick
            }
            delay = int(rule.get("delay_ticks", 0))
            template = rule.get("template")
            if set(agreement.get("participants") or []).issubset(approved):
                agreement["due_tick"] = tick + delay
                agreement["stable_key"] = _stable_template_key(ctx, agreement)
                await _apply_effects_stage(ctx, rule, agreement, "on_start")
                if delay == 0 and not template:
                    await _complete_records(ctx, rule, agreement, tick)
                else:
                    agreement["status"] = "pending"

            receipt = {
                "key": receipt_key,
                "requester": requester,
                "user_key": user_key,
                "partner": partner,
                "rule": rule_id,
                "agreement_id": agreement.get("id"),
            }
            ctx.state.setdefault("agree_receipts", []).append(receipt)
            _truncate(ctx.state)
            return _agreement_summary(agreement)
    except AgreementError:
        raise
    except Exception as error:  # 锁或网络错误统一转为业务错误
        raise AgreementError(str(error))


async def _fulfill_one(ctx, config, parameters):
    agreement_id = parameters.get("id")
    requested_name = parameters.get("name") or "新成员"
    requester = ctx.requester_id
    if not requester:
        raise AgreementError("无法确认请求者身份")

    template_payload = None
    template_key = None
    rule = None
    hint = _find_agreement(ctx.state, agreement_id)
    participants = list((hint or {}).get("participants") or [])
    try:
        async with ctx.network.lock_nodes(
            _lock_order([ctx.node_id] + participants + [config.get("clock")]),
            timeout=20,
        ):
            agreement = _find_agreement(ctx.state, agreement_id)
            if agreement is None:
                raise AgreementError("协议不存在")
            if requester not in (agreement.get("participants") or []):
                raise AgreementError("只有协议参与者可以兑现")
            if agreement.get("status") == "completed":
                return _agreement_summary(agreement, duplicate=True)
            if agreement.get("status") != "pending":
                raise AgreementError("协议尚未达成，不能兑现")
            tick = await _current_tick(ctx, config.get("clock"))
            due_tick = agreement.get("due_tick")
            if due_tick is None or tick < due_tick:
                raise AgreementError("协议尚未到兑现时间")
            delivery = config.get("delivery_address")
            if delivery:
                location = await _node_location(ctx, requester)
                if location != delivery:
                    raise AgreementError("请求者必须到达兑现地点")
            rule = _rule_by_id(config, agreement.get("rule"))
            if rule is None:
                raise AgreementError("协议规则已不存在")
            requester_values = await _node_values(ctx, requester)
            _check_fulfill_requirements(rule, requester_values)
            template = rule.get("template")
            if not template:
                await _complete_records(ctx, rule, agreement, tick)
                return _agreement_summary(agreement)

            if not delivery:
                raise AgreementError("未配置协议兑现地点")
            participant_ids = list(agreement.get("participants") or [])
            left_values = await _node_values(ctx, participant_ids[0])
            right_values = await _node_values(ctx, participant_ids[1])
            home = left_values.get("home")
            if home in (None, "") or home != right_values.get("home"):
                raise AgreementError("双方住所不一致，无法创建家庭")
            pending = agreement.get("pending")
            if pending is None:
                fulfill_cost = int(rule.get("fulfill_cost", 0))
                if fulfill_cost > 0:
                    if requester_values.get("ap", 0) < fulfill_cost:
                        raise AgreementError("行动点不足，无法兑现协议")
                    await _apply(
                        ctx,
                        requester,
                        {"deltas": {"ap": -fulfill_cost}},
                        _fee_key(ctx, agreement, requester, "fulfill-cost"),
                    )
                stable_key = agreement.get("stable_key") or _stable_template_key(
                    ctx, agreement
                )
                pending = {
                    "template": template,
                    "key": stable_key,
                    "arguments": {
                        "name": requested_name,
                        "parents": participant_ids,
                        "home": home,
                    },
                    "returned_node_ids": [],
                }
                agreement["pending"] = pending
                agreement["stable_key"] = stable_key
            else:
                if requested_name != pending.get("arguments", {}).get("name"):
                    raise AgreementError("重试参数与已保存的模板请求不一致")
            template_payload = {
                "template": pending.get("template"),
                "key": pending.get("key"),
                "arguments": _plain(pending.get("arguments")),
            }
            template_key = pending.get("key")
    except AgreementError:
        raise
    except Exception as error:
        raise AgreementError(str(error))

    try:
        result = await ctx.network.invoke(
            config.get("delivery_address"), "templates:instantiate", template_payload
        )
    except Exception as error:
        raise AgreementError("模板兑现失败，可稍后重试：" + str(error))

    node_ids = _extract_node_ids(result)
    if not node_ids:
        raise AgreementError("模板未返回有效节点 ID，协议未完成，可重试")
    try:
        completed_hint = _find_agreement(ctx.state, agreement_id)
        completed_participants = list((completed_hint or {}).get("participants") or [])
        async with ctx.network.lock_nodes(
            _lock_order(
                [ctx.node_id] + completed_participants + [config.get("clock")]
            ),
            timeout=20,
        ):
            agreement = _find_agreement(ctx.state, agreement_id)
            if agreement is None:
                raise AgreementError("协议不存在")
            if agreement.get("status") == "completed":
                return _agreement_summary(agreement, duplicate=True)
            if agreement.get("status") != "pending":
                raise AgreementError("协议状态已改变")
            tick = await _current_tick(ctx, config.get("clock"))
            pending = agreement.get("pending") or {}
            if pending.get("key") != template_key:
                raise AgreementError("模板请求与待办不一致")
            stored = list(pending.get("returned_node_ids") or [])
            for node_id in node_ids:
                if node_id not in stored:
                    stored.append(node_id)
            pending["returned_node_ids"] = stored
            agreement["returned_node_ids"] = [
                {"node_id": node_id} for node_id in stored
            ]
            await _complete_records(ctx, rule, agreement, tick)
            await _add_child_references(ctx, agreement, stored)
            return _agreement_summary(agreement)
    except AgreementError:
        raise
    except Exception as error:
        raise AgreementError(str(error))


async def _fulfill_via_sources(ctx, sources, parameters):
    """先用来源 inspect 定位协议，再只转调唯一匹配的来源一次。

    来源只返回当前 requester 可见的协议；不会执行其他来源来“碰运气”。
    来源的真实业务失败直接抛给调用者，不吞掉，也不继续尝试其他来源。
    """
    agreement_id = parameters.get("id")
    matches = []
    for source in sources:
        data = await _source_inspect(ctx, source)
        found = any(
            isinstance(item, dict) and item.get("id") == agreement_id
            for item in data.get("agreements") or []
        )
        if found and source not in matches:
            matches.append(source)

    if not matches:
        raise AgreementError("没有来源找到该协议：" + str(agreement_id))
    if len(matches) > 1:
        raise AgreementError(
            "协议 ID 在多个来源中匹配，存在歧义，无法确定兑现来源："
            + "、".join(str(source) for source in matches)
        )

    source = matches[0]
    try:
        result = await ctx.network.call(
            source, ctx.module_id, "fulfill", _plain(parameters)
        )
    except Exception as error:
        raise AgreementError(
            "来源兑现失败：" + str(source) + "：" + str(error)
        )
    if result.get("status") != "ok":
        raise AgreementError(
            result.get("error") or ("来源节点兑现失败：" + str(source))
        )
    return {
        "forwarded": True,
        "source": source,
        "sources": [
            {"source": source, "data": _plain(result.get("data"))}
        ],
    }


async def _fulfill(ctx, config, parameters):
    sources = list(config.get("sources") or [])
    if sources:
        return await _fulfill_via_sources(ctx, sources, parameters)

    agreement = _find_agreement(ctx.state, parameters.get("id"))
    return await _fulfill_one(ctx, config, parameters)


async def execute(ctx, activation):
    if activation.kind != "access":
        return ComponentResult(status="error", error="不支持的请求")
    config = _plain(ctx.config)
    operation = activation.operation
    parameters = _plain(activation.parameters or {})
    if operation in ("agree", "fulfill") and not config.get("clock"):
        return ComponentResult(status="error", error="未配置时钟节点")
    if operation not in ("inspect", "agree", "fulfill"):
        return ComponentResult(status="error", error="不支持的请求")

    try:
        if operation == "inspect":
            return ComponentResult(data=await _inspect(ctx, config))
        if operation == "agree":
            return ComponentResult(data=await _agree(ctx, config, parameters))
        return ComponentResult(data=await _fulfill(ctx, config, parameters))
    except AgreementError as error:
        return ComponentResult(status="error", error=str(error))
