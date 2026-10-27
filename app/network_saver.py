"""网络结构存取；数据节点选择保留源文件引用或生成文件副本。"""

from dataclasses import asdict
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from domain.core import (
    Aggregation, AverageAggregation, MaxAggregation, MinAggregation, SumAggregation,
)
from domain.core import DataNode
from domain.core import Link, Multiplier
from domain.core import MarkdownNode
from domain.core import Network
from domain.core import Node
from domain.core import NodeInfo


class NetworkSaver:
    def __init__(self) -> None:
        # 数据节点接收 info、path、save_data 及自身 parameters，负责装配访问器和保存器。
        self.node_types: dict[str, type[DataNode]] = {"markdown": MarkdownNode}
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
            document = {"nodes": [self._encode_node(node, path, copies) for node in network]}
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
                copy.unlink(missing_ok=True)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load(self, path: str | Path) -> Network:
        path = Path(path).resolve()
        document = json.loads(path.read_text(encoding="utf-8"))
        network = Network()
        for record in document["nodes"]:
            info = NodeInfo(**record["info"])
            data = record.get("data")
            if data is None:
                node = Node(info)
            else:
                kind = data["type"]
                if kind not in self.node_types:
                    raise ValueError(f"未知的数据节点类型：{kind}")
                data_path = Path(data["path"])
                if not data_path.is_absolute():
                    data_path = path.parent / data_path
                node = self.node_types[kind](info, data_path, save_data=data["save_data"], **data.get("parameters", {}))
            node.bias = record.get("bias", 0)
            aggregation = record.get("aggregation", "sum")
            if aggregation not in self.aggregation_types:
                raise ValueError(f"未知的节点汇合方法：{aggregation}")
            node.aggregation = self.aggregation_types[aggregation]()
            for config in record.get("links", []):
                node.links.add(self._decode_link(config))
            network.add(node)
        self._check_targets(network)
        return network

    def _encode_node(self, node: Node, config_path: Path, copies: list[Path]) -> dict:
        record = {
            "info": asdict(node.info),
            "bias": node.bias,
            "aggregation": self._encode_aggregation(node.aggregation),
            "links": [self._encode_link(link) for link in node.links],
        }
        if not isinstance(node, DataNode):
            return record
        kind = node.saver.kind
        if kind not in self.node_types:
            raise ValueError(f"尚未登记的数据节点类型：{kind}")
        source = node.saver.path.resolve()
        if node.save_data:
            directory = config_path.parent / f"{config_path.stem}_data"
            directory.mkdir(parents=True, exist_ok=True)
            # 先分配本次拥有的新文件，失败清理不会碰到源文件或旧副本。
            with NamedTemporaryFile(
                dir=directory, prefix="snapshot-", suffix=source.suffix, delete=False,
            ) as stream:
                destination = Path(stream.name)
            copies.append(destination)
            node.saver.save(destination)
            reference = destination.relative_to(config_path.parent).as_posix()
        else:
            # 只记录路径，不调用数据保存方法，也不读写源文件内容。
            reference = str(source)
        record["data"] = {"type": kind, "path": reference, "save_data": node.save_data}
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
        }

    @staticmethod
    def _decode_link(config: dict) -> Link:
        fields = dict(config)
        processor = dict(fields.pop("processor", {}))
        if processor.pop("type", "multiplier") != "multiplier":
            raise ValueError("未知的连接处理器类型")
        return Link(**fields, processor=Multiplier(**processor))

    @staticmethod
    def _check_targets(network: Network) -> None:
        for node in network:
            for link in node.links:
                if network.get(link.target_id) is None:
                    raise ValueError(f"节点 {node.info.node_id} 的连接目标不存在：{link.target_id}")
