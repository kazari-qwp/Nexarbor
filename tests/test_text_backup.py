"""Ordinary text tools keep old write modes, backups and node rollback."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.data.text import TextFileAccess
from app.runtime.backend import Backend
from app.studio.data_preview import preview
from app.studio.testing import ModuleHarness
from app.transactions import NodeLocks, NodeSnapshots
from domain.core import MarkdownNode, Network, NodeInfo

ROOT = Path(__file__).resolve().parents[1]


class TextBackupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(ROOT / "projects/knowledge_archive/modules/data_local")
        self.addAsyncCleanup(self.h.close)
        self.node = self.h.add_text("note", "original\n")
        self.h.mount("note")
        self.original_bytes = self.node.saver.path.read_bytes()
        self.original_text = self.node.dataer.read()
        self.backup = self.node.saver.path.with_name(self.node.saver.path.name + ".bak")

    async def write(self, value, mode="upsert"):
        return (await self.h.call("note", "write", dict(key="content", value=value, mode=mode)))["data"]

    async def test_real_module_append_previous_bytes_and_cold_reopen(self):
        first = await self.write("replacement")
        self.assertEqual(first.status, "ok")
        self.assertEqual(first.items, [dict(node_id="note", written=True)])
        self.assertEqual(self.backup.read_bytes(), self.original_bytes)
        await self.write("+suffix", "append")
        self.assertEqual(self.node.dataer.read(), "replacement+suffix")
        self.assertEqual(self.backup.read_bytes(), b"replacement")
        self.assertEqual((await self.write("conflict", "insert")).status, "conflict")
        await self.h.restart()
        self.node = self.h.network.get("note")
        self.assertEqual(self.backup.read_bytes(), b"replacement")
        self.assertEqual(self.node.dataer.read(), "replacement+suffix")
        self.node.modules.get("data.local").config["read_only"] = True
        with self.assertRaisesRegex(PermissionError, "只读"):
            await self.write("forbidden")

    async def test_failures_restore_both_files_and_remove_a_new_backup(self):
        async def fail_after_write():
            async with self.h.backend.node_locks.transaction(["note"]):
                TextFileAccess(self.node).write("content", "changed")
                raise RuntimeError("abort")
        with self.assertRaisesRegex(RuntimeError, "abort"):
            await fail_after_write()
        self.assertEqual(self.node.dataer.read(), self.original_text)
        self.assertFalse(self.backup.exists())
        self.backup.write_bytes(b"older\r\n")
        with self.assertRaisesRegex(RuntimeError, "abort"):
            await fail_after_write()
        self.assertEqual(self.backup.read_bytes(), b"older\r\n")
        self.assertEqual(self.node.dataer.read(), self.original_text)

    async def test_backup_owned_by_another_node_requires_a_joint_lock(self):
        self.backup.write_text("shared", encoding="utf-8")
        other = MarkdownNode(NodeInfo("other", "Other"), self.backup)
        self.h.network.add(other)
        with self.assertRaisesRegex(ValueError, "locked together"):
            async with self.h.backend.node_locks.transaction(["note"]):
                pass

    async def test_preview_isolated_write_and_character_budget(self):
        self.h.backend.save()
        snapshot = self.h.backend.snapshot()
        record = next(n for n in snapshot["network"]["nodes"] if n["node_id"] == "note")
        result = preview(self.h.backend, dict(node=record, files=snapshot["files"], operation="write", arguments=dict(key="content", value="preview")))
        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(result["files"][record["data"]["path"]], "preview")
        self.assertEqual(result["files"][record["data"]["path"] + ".bak"], self.original_bytes.decode("utf-8"))
        self.assertEqual(self.node.dataer.read(), self.original_text)
        self.assertFalse(self.backup.exists())
        service = TextFileAccess(self.node, max_chars=3)
        self.assertEqual(service.write("content", "longer").status, "error")
        self.assertFalse(self.backup.exists())
        self.assertEqual(service.write("elsewhere", "x").status, "not_found")
