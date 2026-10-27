"""实际 15 节点讨论项目的装配、上下文、工具和保存恢复。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adapt.harness.executor import NativeExecutor
from app.runtime.requester import as_requester
from domain.core import DataNode
from projects.discussion_collaboration.runtime import DiscussionProject
from app.projects.host_tools import host_tool_name

ROOT = Path(__file__).resolve().parents[1]


class DiscussionProjectTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix=".discussion-project-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.project = DiscussionProject(self.temp.name)
        self.addCleanup(lambda:self.project.close())

    async def test_actual_project_keeps_nodes_resources_modules_and_host_tools(self):
        backend = self.project.backend
        self.assertEqual(len(list(backend.network)), 15)
        self.assertEqual(len(backend.bindings), 10)
        data_nodes = [node for node in backend.network if isinstance(node, DataNode)]
        self.assertEqual(len(data_nodes), 12)
        self.assertTrue(all(node.saver.path.resolve().is_relative_to(Path(self.temp.name).resolve()) for node in data_nodes))
        self.assertEqual(sum(tool.name.startswith("ext_") for node in backend.network for tool in node.tools), 31)
        self.assertEqual(len(backend.snapshot()["files"]), 12)
        group = backend.network.get("collab")
        integrator = group.modules.get("git.integrator.rev_2863bbe53e.rev_c376775a7e")
        self.assertEqual(integrator.config["terminal_ref"], host_tool_name("collab", "harness:pwsh"))
        self.assertTrue(any(tool.name == integrator.config["terminal_ref"] for tool in group.tools))

    async def test_real_agent_prepare_reads_markdown_context_and_excludes_other_agents_memory(self):
        backend = self.project.backend
        backend.network.get("recorder").dataer.write("OTHER_PRIVATE_MEMORY")
        executor = NativeExecutor(backend.network, None, bindings=backend.bindings, states=backend.agents, locks=backend.node_locks)
        view = await executor.prepare({"actor":"leader"})
        self.assertTrue(view["context"])
        text = "\n".join(doc["text"] for doc in view["context"])
        self.assertIn("讨论", text)
        self.assertNotIn("OTHER_PRIVATE_MEMORY", text)
        names = {tool["name"] for tool in view["tools"]}
        recorder_run = host_tool_name("recorder", "runtime:agent_run")
        self.assertNotIn(recorder_run, names)
        self.assertIn("memory_query", names)

    async def test_host_tool_factory_keeps_original_requester_and_survives_cold_reopen(self):
        calls = []
        async def official(actor, name, arguments):
            calls.append((actor, name, arguments))
            return {"format":"harness-tool-result/v1", "value":{"kind":"foreground", "exitCode":0}}
        self.project.official_port = official
        name = host_tool_name("workspace", "harness:read")
        executor = NativeExecutor(self.project.backend.network, None, bindings=self.project.backend.bindings,
                                  states=self.project.backend.agents, locks=self.project.backend.node_locks)
        view = await executor.prepare({"actor":"executor-1"})
        self.assertIn(name, {tool["name"] for tool in view["tools"]})
        await executor.invoke({"actor":"executor-1", "name":name, "arguments":{"file_path":"example.py"}})
        self.assertEqual(calls, [("executor-1", "read", {"file_path":"example.py"})])
        names = [tool.name for tool in self.project.backend.network.get("workspace").tools]
        self.project.backend.save()
        self.project.close()
        self.project = DiscussionProject(self.temp.name)
        self.project.official_port = official
        restored = self.project.backend.network.get("workspace")
        self.assertEqual([tool.name for tool in restored.tools], names)
        with as_requester("executor-2"):
            await next(tool for tool in restored.tools if tool.name == name).invoke(file_path="restored.py")
        self.assertEqual(calls[-1], ("executor-2", "read", {"file_path":"restored.py"}))
