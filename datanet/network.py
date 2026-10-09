"""读写分离的网络：读取聚合，写入按范围定向路由。"""

from collections import deque
from collections.abc import Callable
from typing import Any

from datanet.nodes.node import Node, NodeResult


class Network:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.delegation_permissions: dict[str, list[str]] = {}

    def add_node(self, node: Node):
        if node.node_id in self.nodes:
            raise ValueError(f"节点编号重复：{node.node_id}")
        self.nodes[node.node_id] = node

    def get(self, node_id: str, key: str, scope: str = "local",
            data_kind: str | None = None) -> NodeResult:
        return self._read(node_id, scope, data_kind, lambda node: node.get(key))

    def query(self, node_id: str, filters: dict[str, Any], scope: str = "local",
              data_kind: str | None = None) -> NodeResult:
        return self._read(node_id, scope, data_kind, lambda node: node.query(filters))

    def weak_read(self, node_id: str, key: str,
                  data_kind: str | None = None) -> NodeResult:
        """弱访问：本体及沿强读连接可达的数据。"""
        return self.get(node_id, key, scope="integrated", data_kind=data_kind)

    def strong_read(self, node_id: str, key: str,
                    data_kind: str | None = None) -> NodeResult:
        """强访问：本体及沿强、弱读连接可达的数据。"""
        return self.get(node_id, key, scope="federated", data_kind=data_kind)

    def weak_write(self, node_id: str, target_node_id: str, key: str, value: Any,
                   *, mode: str = "upsert") -> NodeResult:
        """只沿强写连接寻找指定目标，包含起点本体。"""
        return self._write(node_id, target_node_id, key, value, mode, False)

    def strong_write(self, node_id: str, target_node_id: str, key: str, value: Any,
                     *, mode: str = "upsert") -> NodeResult:
        """沿强、弱写连接寻找指定目标，只写入一次。"""
        return self._write(node_id, target_node_id, key, value, mode, True)

    def _write(self, node_id, target_node_id, key, value, mode, include_weak):
        from datanet.nodes.write_support import validate_write
        validate_write(key, mode)
        if not isinstance(node_id, str) or not isinstance(target_node_id, str):
            raise TypeError("起点和目标编号必须是字符串")
        if node_id not in self.nodes or target_node_id not in self.nodes:
            return NodeResult(status="error", errors=["起点或目标节点不存在"])
        queue = deque([(node_id, [node_id])])
        visited = set()
        while queue:
            current_id, path = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            node = self.nodes.get(current_id)
            if node is None:
                continue
            if current_id == target_node_id:
                result = node.write(key, value, mode=mode)
                result.sources = [{**source, "write_path": path.copy()} for source in result.sources]
                return result
            interfaces = list(node.strong_write_interfaces)
            if include_weak:
                interfaces.extend(node.weak_write_interfaces)
            queue.extend((i.target_node_id, [*path, i.target_node_id]) for i in interfaces)
        return NodeResult(status="forbidden", errors=["目标不在当前写入范围内"])

    def _read(self, node_id: str, scope: str, data_kind: str | None,
              read_local: Callable[[Node], NodeResult | None]) -> NodeResult:
        if scope not in {"local", "integrated", "federated"}:
            raise ValueError(f"未知访问范围：{scope}")
        if node_id not in self.nodes:
            return NodeResult(status="error", errors=[f"节点不存在：{node_id}"])

        result = NodeResult()
        queue = deque([(node_id, [node_id])])
        visited = set()
        successful_read = False
        while queue:
            current_id, path = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            node = self.nodes.get(current_id)
            if node is None:
                result.errors.append(f"接口目标不存在：{current_id}")
                continue

            if data_kind is None or node.data_kind == data_kind:
                local_result = read_local(node)
                if local_result is not None:
                    if local_result.status == "ok":
                        successful_read = True
                    elif local_result.status != "not_found":
                        result.errors.extend(local_result.errors or [
                            f"节点 {current_id} 读取失败：{local_result.status}"
                        ])
                    result.items.extend(local_result.items)
                    result.sources.extend(
                        {**source, "retrieval_path": list(path)}
                        for source in local_result.sources
                    )

            if scope == "local":
                continue
            interfaces = list(node.strong_read_interfaces)
            if scope == "federated":
                interfaces.extend(node.weak_read_interfaces)
            for interface in interfaces:
                target = interface.target_node_id
                queue.append((target, [*path, target]))

        if result.errors:
            result.status = "error"
        elif successful_read:
            # 成功的条件查询可以没有匹配行；不存在可读节点则不同。
            result.status = "ok"
        else:
            result.status = "not_found"
        return result
