import asyncio
import json
import sys
import unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import module as metadata_fields
from datanet.core.json_values import FrozenDict, freeze, thaw
from datanet.core.module_protocol import Activation, ComponentResult, ModuleDefinition
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.node_modules import NodeModules
from datanet.core.signals import Signal

MODULE_ID = "metadata.fields"
MANIFEST = json.loads((ROOT / "module.json").read_text(encoding="utf-8"))

# 使用真实清单构造组件定义，避免另写一套测试专用操作或放宽配置校验。
DEFINITION = ModuleDefinition(
    metadata_fields.execute,
    operations=MANIFEST["operations"],
    signals=MANIFEST["signals"],
    node_types=MANIFEST["node_types"],
    config_schema=MANIFEST["config_schema"],
    state_schema=MANIFEST["state_schema"],
)


async def caller_execute(ctx, activation):
    if activation.kind != "access" or activation.operation != "forward":
        return ComponentResult(status="error", error="不支持的操作。")
    target = activation.parameters["target"]
    channels = list(activation.parameters.get("channels", []))
    result = await ctx.network.call(target, MODULE_ID, "read", {}, channels=channels)
    return ComponentResult(data=result)


CALLER_DEFINITION = ModuleDefinition(
    caller_execute,
    operations=[
        {
            "name": "forward",
            "channels": ["metadata", "其他"],
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "channels": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["target"],
                "additionalProperties": False,
            },
            "result": {"type": "object"},
        }
    ],
    node_types=["node"],
)


def make_backend(*node_ids):
    network = Network()
    for node_id in node_ids:
        network.add_node(Node(node_id, node_id, None))
    backend = SimpleNamespace(
        network=network,
        _transaction_lock=RLock(),
        components=SimpleNamespace(
            module_owners={MODULE_ID: "测试组件"},
            module_extensions={},
            enabled={"测试组件"},
        ),
    )
    backend.signals = network.signals
    backend.modules = NodeModules(
        backend, {MODULE_ID: DEFINITION, "测试调用方": CALLER_DEFINITION}
    )
    return backend


def mount(backend, node_id, config, *, channels=("metadata",), strength=2):
    return backend.modules.mount(
        node_id,
        MODULE_ID,
        config,
        access={"strength": strength, "channels": list(channels)},
    )


def published_extension(backend, node_id):
    return backend.network.get_metadata(node_id).get("extensions", {}).get(MODULE_ID)


def sample_fields():
    return {
        "标题": "示例",
        "计数": 3,
        "比例": 1.5,
        "启用": True,
        "停用": False,
        "空值": None,
        "配置": {"层级": {"值": 2}, "列表": [1, "二", False, None]},
        "列表": [1, 2.5, "三", {"键": "值"}],
    }


class RecordingContext:
    """只记录发布内容的测试上下文；Signal 与 Activation 仍使用核心真实类型。"""

    def __init__(self, config, state=None):
        self.config = config
        self.state = {} if state is None else state
        self.node_id = "甲"
        self.published = []

    def publish_metadata(self, fields):
        self.published.append(thaw(fields))


class ReadIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_through_real_node_modules_publishes_and_returns_json_types(self):
        backend = make_backend("甲")
        fields = sample_fields()
        instance = mount(backend, "甲", {"fields": fields})

        result = await backend.modules.call("甲", MODULE_ID, "read")

        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["error"])
        self.assertEqual(result["data"], {"fields": fields})
        self.assertEqual(published_extension(backend, "甲"), fields)

        returned = result["data"]["fields"]
        self.assertIs(type(returned["计数"]), int)
        self.assertIs(type(returned["比例"]), float)
        self.assertIs(type(returned["启用"]), bool)
        self.assertIs(type(returned["停用"]), bool)
        self.assertIsNone(returned["空值"])
        self.assertIs(type(returned["配置"]), dict)
        self.assertIs(type(returned["列表"]), list)
        self.assertEqual(returned["配置"]["列表"], [1, "二", False, None])

        self.assertIsInstance(instance.config, FrozenDict)
        with self.assertRaises(TypeError):
            instance.config["fields"] = {}
        self.assertEqual(instance.state, {})

    async def test_returned_copy_cannot_change_config_or_published_metadata(self):
        backend = make_backend("甲")
        fields = sample_fields()
        instance = mount(backend, "甲", {"fields": fields})

        result = await backend.modules.call("甲", MODULE_ID, "read")
        result["data"]["fields"]["配置"]["层级"]["值"] = 99
        result["data"]["fields"]["列表"].append("新增")

        self.assertEqual(thaw(instance.config["fields"]), fields)
        self.assertEqual(published_extension(backend, "甲"), fields)

    async def test_missing_and_empty_fields_publish_empty_object(self):
        backend = make_backend("甲", "乙")
        mount(backend, "甲", {})
        mount(backend, "乙", {"fields": {}})

        first = await backend.modules.call("甲", MODULE_ID, "read")
        second = await backend.modules.call("乙", MODULE_ID, "read")

        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "ok")
        self.assertEqual(first["data"], {"fields": {}})
        self.assertEqual(second["data"], {"fields": {}})
        self.assertEqual(published_extension(backend, "甲"), {})
        self.assertEqual(published_extension(backend, "乙"), {})

    async def test_two_instances_do_not_share_fields_state_or_results(self):
        backend = make_backend("甲", "乙")
        first = {"名称": "甲", "数量": 1, "标签": ["独立"]}
        second = {"名称": "乙", "数量": 2, "配置": {"可用": True}}
        instance_a = mount(backend, "甲", {"fields": first})
        instance_b = mount(backend, "乙", {"fields": second})

        result_a, result_b = await asyncio.gather(
            backend.modules.call("甲", MODULE_ID, "read"),
            backend.modules.call("乙", MODULE_ID, "read"),
        )

        self.assertEqual(result_a["status"], "ok")
        self.assertEqual(result_b["status"], "ok")
        self.assertEqual(result_a["data"], {"fields": first})
        self.assertEqual(result_b["data"], {"fields": second})
        self.assertEqual(published_extension(backend, "甲"), first)
        self.assertEqual(published_extension(backend, "乙"), second)

        result_a["data"]["fields"]["标签"].append("污染")
        result_b["data"]["fields"]["配置"]["可用"] = False
        self.assertEqual(published_extension(backend, "甲"), first)
        self.assertEqual(published_extension(backend, "乙"), second)
        self.assertIsNot(instance_a.config, instance_b.config)
        self.assertEqual(instance_a.state, {})
        self.assertEqual(instance_b.state, {})

    async def test_repeated_reads_each_succeed_and_keep_published_fields(self):
        backend = make_backend("甲")
        fields = {"次数": 1, "说明": "重复读取"}
        mount(backend, "甲", {"fields": fields})

        results = [await backend.modules.call("甲", MODULE_ID, "read") for _ in range(3)]

        for result in results:
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["data"], {"fields": fields})
            self.assertEqual(published_extension(backend, "甲"), fields)


class SignalIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_signal_propagation_publishes_on_each_target(self):
        backend = make_backend("来源", "甲", "乙")
        origin = backend.network.nodes["来源"]
        origin.connect("甲", channels=["metadata.refresh"])
        origin.connect("乙", channels=["metadata.refresh"])
        fields_a = {"状态": "在线", "版本": 2, "可选": None}
        fields_b = {"状态": "离开", "标签": ["乙"]}
        mount(backend, "甲", {"fields": fields_a})
        mount(backend, "乙", {"fields": fields_b})

        signal = Signal(
            "来源",
            ["metadata.refresh"],
            2,
            content={"说明": "刷新元数据"},
            node_timeout_seconds=10,
            timeout_seconds=15,
        )
        report = await backend.network.propagate(signal)

        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["returned"], False)
        self.assertCountEqual(report["layers"][-1], ["甲", "乙"])
        for delivery in report["deliveries"]:
            self.assertEqual(delivery["status"], "processed")
            self.assertEqual(delivery["value"][0]["status"], "ok")
        self.assertEqual(published_extension(backend, "甲"), fields_a)
        self.assertEqual(published_extension(backend, "乙"), fields_b)

    async def test_repeated_signal_deliveries_publish_again_and_keep_isolation(self):
        backend = make_backend("来源", "甲")
        backend.network.nodes["来源"].connect("甲", channels=["metadata.refresh"])
        fields = {"刷新次数": 1, "配置": {"层级": [1, 2]}}
        mount(backend, "甲", {"fields": fields})

        first = await backend.network.propagate(
            Signal("来源", ["metadata.refresh", "附加"], 2)
        )
        second = await backend.network.propagate(
            Signal("来源", ["metadata.refresh"], 2)
        )

        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(published_extension(backend, "甲"), fields)
        self.assertEqual(backend.modules.get("甲", MODULE_ID).state, {})

    async def test_signal_without_refresh_channel_does_not_publish(self):
        backend = make_backend("来源", "甲")
        backend.network.nodes["来源"].connect("甲", channels=["metadata.other"])
        mount(backend, "甲", {"fields": {"不应发布": True}})

        report = await backend.network.propagate(
            Signal("来源", ["metadata.other"], 2)
        )

        self.assertEqual(report["status"], "completed")
        self.assertEqual(len(report["deliveries"]), 1)
        self.assertEqual(report["deliveries"][0]["node_id"], "甲")
        self.assertIsNone(published_extension(backend, "甲"))


class ActivationAndErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_execute_returns_frozen_component_result(self):
        fields = sample_fields()
        ctx = RecordingContext(freeze({"fields": fields}))
        activation = Activation("access", "read", {}, "来源", request_id="req-read")

        result = await metadata_fields.execute(ctx, activation)

        self.assertIsInstance(result, ComponentResult)
        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.error)
        self.assertIsInstance(result.data, FrozenDict)
        self.assertIsInstance(result.data["fields"], FrozenDict)
        self.assertIsInstance(result.data["fields"]["列表"], tuple)
        self.assertIsInstance(result.data["fields"]["列表"][3], FrozenDict)
        self.assertIsInstance(result.data["fields"]["配置"]["列表"], tuple)
        with self.assertRaises(TypeError):
            result.data["fields"]["标题"] = "修改"
        self.assertEqual(ctx.published, [fields])

    async def test_real_signal_channel_matching_uses_signal_channels(self):
        ctx = RecordingContext(freeze({"fields": {"来源": "本地"}}))
        bad_signal = Signal("来源", ["metadata.other"], 2)
        bad_activation = Activation(
            "signal", "request", {}, "来源", signal=bad_signal, request_id="req-bad"
        )

        bad_result = await metadata_fields.execute(ctx, bad_activation)

        self.assertEqual(bad_result.status, "error")
        self.assertIn("不支持的信号频道", bad_result.error)
        self.assertIn("metadata.other", bad_result.error)
        self.assertEqual(ctx.published, [])

        good_signal = Signal("来源", ["metadata.other", "metadata.refresh"], 2)
        good_activation = Activation(
            "signal", "request", {}, "来源", signal=good_signal, request_id="req-good"
        )
        good_result = await metadata_fields.execute(ctx, good_activation)

        self.assertEqual(good_result.status, "ok")
        self.assertEqual(good_result.data, {"fields": {"来源": "本地"}})
        self.assertEqual(ctx.published, [{"来源": "本地"}])

    async def test_missing_signal_object_returns_chinese_error(self):
        ctx = RecordingContext(freeze({"fields": {"来源": "本地"}}))
        activation = Activation("signal", "request", {}, "来源", request_id="req-none")

        result = await metadata_fields.execute(ctx, activation)

        self.assertEqual(result.status, "error")
        self.assertIn("不支持的信号频道", result.error)
        self.assertIn("未提供", result.error)
        self.assertEqual(ctx.published, [])

    async def test_invalid_fields_config_returns_error_without_publishing(self):
        for bad in ([], "文本", 3, 1.5, True, None):
            ctx = RecordingContext(freeze({"fields": bad}))
            result = await metadata_fields.execute(
                ctx, Activation("access", "read", {}, "来源")
            )

            self.assertEqual(result.status, "error")
            self.assertIn("fields", result.error)
            self.assertIn("对象", result.error)
            self.assertEqual(ctx.published, [])

    async def test_unclaimed_operation_is_rejected_by_host_and_module(self):
        backend = make_backend("甲")
        mount(backend, "甲", {"fields": {"名称": "甲"}})
        with self.assertRaises(ValueError):
            await backend.modules.call("甲", MODULE_ID, "write")

        ctx = RecordingContext(freeze({"fields": {"名称": "甲"}}))
        result = await metadata_fields.execute(
            ctx, Activation("access", "write", {}, "来源")
        )
        self.assertEqual(result.status, "error")
        self.assertIn("不支持的操作", result.error)
        self.assertEqual(ctx.published, [])

    async def test_mount_rejects_non_object_fields_before_reading(self):
        backend = make_backend("甲")
        with self.assertRaises(Exception):
            mount(backend, "甲", {"fields": []})
        self.assertIsNone(published_extension(backend, "甲"))
        self.assertEqual(backend.modules.instances, {})

    async def test_read_operation_requires_metadata_channel(self):
        backend = make_backend("甲", "调用方一", "调用方二")
        mount(backend, "甲", {"fields": {"来源": "本地"}})
        backend.network.nodes["调用方一"].connect("甲", channels=["metadata"])
        backend.network.nodes["调用方二"].connect("甲", channels=["其他"])
        backend.modules.mount(
            "调用方一",
            "测试调用方",
            access={"strength": 2, "channels": ["metadata"]},
        )
        backend.modules.mount(
            "调用方二",
            "测试调用方",
            access={"strength": 2, "channels": ["其他"]},
        )

        allowed = await backend.modules.call(
            "调用方一",
            "测试调用方",
            "forward",
            {"target": "甲", "channels": ["metadata"]},
        )
        self.assertEqual(allowed["status"], "ok")
        self.assertEqual(allowed["data"]["status"], "ok")
        self.assertEqual(
            allowed["data"]["data"], {"fields": {"来源": "本地"}}
        )

        with self.assertRaises(PermissionError):
            await backend.modules.call(
                "调用方二",
                "测试调用方",
                "forward",
                {"target": "甲", "channels": ["其他"]},
            )


if __name__ == "__main__":
    unittest.main()
