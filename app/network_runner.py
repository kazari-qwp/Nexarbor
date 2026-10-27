"""持有内存网络，等待外部操作或关闭信号，不主动推进网络。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event, RLock
from typing import Any

from domain.core import Network
from .network_saver import NetworkSaver


class NetworkRunner:
    def __init__(self, network: Network) -> None:
        self._network = network
        self._closed = Event()
        self._lock = RLock()

    @classmethod
    def from_file(cls, path: str | Path) -> NetworkRunner:
        """启动时加载一次，后续操作直接使用内存网络。"""
        return cls(NetworkSaver().load(path))

    @property
    def network(self) -> Network:
        return self._network

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def run(self) -> None:
        """阻塞等待关闭，用于维持进程生命周期；外部触发无需依赖轮询。"""
        self._closed.wait()

    def trigger(self, operation: Callable[[Network], Any]) -> Any:
        """同步执行一次外部操作；同一运行器的操作依次执行。"""
        with self._lock:
            if self.closed:
                raise RuntimeError("网络运行器已经关闭")
            return operation(self._network)

    def close(self) -> None:
        """等待当前外部操作完成，停止接收新操作并唤醒 run()。"""
        with self._lock:
            self._closed.set()
