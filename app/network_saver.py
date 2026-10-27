"""网络结构存取；数据节点选择保留源文件引用或生成文件副本。"""

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import NamedTemporaryFile, mkdtemp
from shutil import rmtree

from domain.core import (
    Aggregation, AverageAggregation, MaxAggregation, MinAggregation, SumAggregation,
)
from domain.core import DataNode
from domain.core import Link, Multiplier
from domain.core import MarkdownNode
from domain.core import Network
from domain.core import Node
from domain.core import NodeInfo
from domain.agent import AgentNode, MarkdownAgentNode
from domain.agent.inputs import AgentInputs
from domain.pulse_node import PulseNode
from domain.annotated_link import AnnotatedLink
from domain.json_values import thaw
from .persistence.tables import ModuleTables


class NetworkSaver:
    def __init__(self, *, read_text=None) -> None:
        self.tables = ModuleTables(read_text=read_text)
        self.node_types: dict[str, type[DataNode]] = {"markdown": MarkdownNode}
        self.agent_node_types: dict[str, type[AgentNode]] = {"markdown": MarkdownAgentNode}
        self.aggregation_types: dict[str, type[Aggregation]] = {
            "sum": SumAggregation,
            "max": MaxAggregation,
            "min": MinAggregation,
            "average": AverageAggregation,
        }

    def save(self, network: Network, path: str | Path) -> None:
        """先生成数据副本，再替换配置；失败时撤销本次新建文件。"""
        self._check_targets(network)
        path = Path(path).resolve()
        copies: list[Path] = []
        temporary = None
        try:
            document = self.document(network, path.parent, copies=copies, data_directory=path.stem + "_data")
            content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            temporary.replace(path)
        except Exception:
            for copy in copies:
                directory = (path.parent / f"{path.stem}_data").resolve()
                if copy.is_symlink():
                    copy.unlink()
                elif copy.resolve().parent != directory:
                    raise RuntimeError("拒绝清理本次保存目录之外的文件")
                elif copy.is_dir():
                    rmtree(copy)
                else:
                    copy.unlink(missing_ok=True)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load(self, path: str | Path) -> Network:
        path = Path(path).resolve()
        document = json.loads(path.read_text(encoding="utf-8"))
        return self.build(document, path.parent)

    def document(self, network: Network, base: str | Path, *, node_overrides=None,
                 copies=None, data_directory="network_data") -> dict:
        """生成配置。日志提交保留资源地址；显式导出才按 save_data 生成副本。"""
        base = Path(base).resolve()
        overrides = node_overrides or {}
        return {"nodes": [deepcopy(overrides[node.info.node_id]) if node.info.node_id in overrides
                          else self._encode_node(node, base, copies, data_directory) for node in network]}

    def build(self, document: dict, base: str | Path) -> Network:
        base = Path(base).resolve()
        network = Network()
        for record in document["nodes"]:
            info = NodeInfo(**{key: record[key] for key in ("node_id", "name", "description") if key in record})
            data = record.get("data")
            is_agent = record.get("type") == "agent"
            if data is None:
                if record.get("type","node") not in ("node","agent","pulse"):raise ValueError("未知的节点类型："+str(record.get("type")))
                node = PulseNode(info, **record.get("parameters", {})) if record.get("type") == "pulse" else AgentNode(info) if is_agent else Node(info)
            else:
                kind = data["type"]
                if kind not in self.node_types:
                    raise ValueError(f"未知的数据节点类型：{kind}")
                data_path = Path(data["path"])
                if not data_path.is_absolute():
                    data_path = base / data_path
                node_class = self.agent_node_types[kind] if is_agent else self.node_types[kind]
                node = node_class(info, data_path, save_data=data["save_data"], **data.get("parameters", {}))
            if is_agent:
                node.inputs = AgentInputs(record.get("agent", {}).get("inputs", {}))
            node.bias = record.get("bias", 0)
            aggregation = record.get("aggregation", "sum")
            if aggregation not in self.aggregation_types:
                raise ValueError(f"未知的节点汇合方法：{aggregation}")
            node.aggregation = self.aggregation_types[aggregation]()
            for config in record.get("links", []):
                node.links.add(self._decode_link(config))
            self.tables.restore(node, record.get("tables"))
            network.add(node)
        self._check_targets(network)
        return network

    def _encode_node(self, node: Node, base: Path, copies, data_directory: str) -> dict:
        record = {
            "type": node.node_type,
            **asdict(node.info),
            "tables": self.tables.encode(node),
            "bias": node.bias,
            "aggregation": self._encode_aggregation(node.aggregation),
            "links": [self._encode_link(link) for link in node.links],
        }
        if node.node_type == "pulse":
            record["parameters"] = dict(channels=list(node.channels), strength=node.strength, content=thaw(node.content),
                                        signal_options=thaw(node.signal_options), state=deepcopy(node.state))
        if node.node_type == "agent":
            record["agent"] = {"inputs": node.inputs.snapshot()}
        if not isinstance(node, DataNode):
            return record
        kind = node.saver.kind
        if kind not in self.node_types:
            raise ValueError(f"尚未登记的数据节点类型：{kind}")
        source = node.saver.path.resolve()
        if copies is not None and node.save_data:
            directory = base / data_directory
            directory.mkdir(parents=True, exist_ok=True)
            # 先分配本次拥有的新文件，失败清理不会碰到源文件或旧副本。
            if source.is_dir():
                destination = Path(mkdtemp(dir=directory, prefix="snapshot-"))
            else:
                with NamedTemporaryFile(
                    dir=directory, prefix="snapshot-", suffix=source.suffix, delete=False,
                ) as stream:
                    destination = Path(stream.name)
            copies.append(destination)
            node.saver.save(destination)
            reference = destination.relative_to(base).as_posix()
        else:
            # 只记录路径，不调用数据保存方法，也不读写源文件内容。
            reference = source.relative_to(base).as_posix() if copies is None and source.is_relative_to(base) else str(source)
        record["data"] = {"type": kind, "path": reference, "save_data": node.save_data, "directory": source.is_dir()}
        parameters = getattr(node, "parameters", {})
        if parameters:
            record["data"]["parameters"] = parameters
        return record

    def _encode_aggregation(self, aggregation: Aggregation) -> str:
        for name, aggregation_type in self.aggregation_types.items():
            if type(aggregation) is aggregation_type:
                return name
        raise ValueError("自定义汇合方法需要先登记到 aggregation_types")

    @staticmethod
    def _encode_link(link: Link) -> dict:
        if type(link.processor) is not Multiplier:
            raise ValueError("当前仅支持保存 Multiplier，自定义处理函数需要配置协议")
        return {
            "target_id": link.target_id,
            "channels": list(link.channels),
            "channel_mode": link.channel_mode,
            "threshold": link.threshold,
            "processor": {"type": "multiplier", "factor": link.processor.factor},
            **({"attributes": thaw(link.attributes)} if isinstance(link, AnnotatedLink) else {}),
        }

    @staticmethod
    def _decode_link(config: dict) -> Link:
        fields = dict(config)
        processor = dict(fields.pop("processor", {}))
        if processor.pop("type", "multiplier") != "multiplier":
            raise ValueError("未知的连接处理器类型")
        return (AnnotatedLink if "attributes" in fields else Link)(**fields, processor=Multiplier(**processor))

    @staticmethod
    def _check_targets(network: Network) -> None:
        for node in network:
            for link in node.links:
                if network.get(link.target_id) is None:
                    raise ValueError(f"节点 {node.info.node_id} 的连接目标不存在：{link.target_id}")
