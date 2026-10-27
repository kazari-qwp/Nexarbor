"""运行端口沿用文本根目录/上限和自执行事务边界。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.runtime.backend import Backend
from app.runtime import ports
from domain.agent import AgentNode
from domain.core import Network, Node, NodeInfo

ROOT = Path(__file__).resolve().parents[1]


class RuntimePortTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix=".runtime-ports-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.project = self.directory / "project"
        self.project.mkdir()
        self.backend = Backend(self.directory / "runtime", network=Network([AgentNode(NodeInfo("actor", "Actor")), Node(NodeInfo("plain", "Plain"))]))
        self.addCleanup(self.backend.close)
        self.calls = []
        async def execute(actor, message, **options):
            self.assertIsNone(self.backend.node_locks.current)
            self.calls.append((actor, message))
            return {"status":"completed", "output":"native port fixture"}
        self.backend.agent_executor = execute

    async def test_text_root_and_explicit_external_roots_with_utf8_bom(self):
        outside = self.directory / "outside.md"
        outside.write_bytes(b"\xef\xbb\xbf" + "实际文本".encode())
        with self.assertRaises(PermissionError):ports.read_text(self.project, {"path":str(outside)})
        result = ports.read_text(self.project, {"path":str(outside), "roots":[str(self.directory)]})
        self.assertEqual(result["text"], "实际文本")
        self.assertEqual(result["path"], str(outside.resolve()))

    async def test_text_limit_and_project_environment_are_preserved(self):
        (self.project / "small.md").write_text("project document", encoding="utf-8")
        (self.project / "large.md").write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            ports.read_text(self.project, {"path":"large.md"})
        with patch.dict("os.environ", {"NEXARBOR_PROJECT_DIRECTORY":str(self.project)}):
            result = await ports.execute(self.backend, "actor", "read_text", {"path":"small.md"})
        self.assertEqual(result["text"], "project document")

    async def test_self_agent_port_runs_agent_and_restores_access_scope(self):
        async with self.backend.node_locks.access(["actor"], mutable=False):
            result = await ports.execute(self.backend, "actor", "agent_run", {"message":"go"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.calls, [("actor", "go")])
        with self.assertRaisesRegex(ValueError, "Agent"):
            await ports.execute(self.backend, "plain", "agent_run", {})

    async def test_self_agent_port_rejects_waiting_inside_node_transaction(self):
        async with self.backend.node_locks.transaction(["actor"]):
            with self.assertRaisesRegex(RuntimeError, "节点锁"):
                await ports.execute(self.backend, "actor", "agent_run", {"message":"blocked"})
        self.assertEqual(self.calls, [])

    async def test_checkpoint_port_uses_real_store_and_unknown_port_is_rejected(self):
        result = await ports.execute(self.backend, "actor", "checkpoint", {"full":True})
        self.assertTrue(result)
        self.assertTrue(self.backend.store.latest())
        with self.assertRaisesRegex(ValueError, "未登记"):
            await ports.execute(self.backend, "actor", "unknown", {})
