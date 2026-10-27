"""显式更新项目源配置中的协作模块工具表；不修改运行中网络。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from projects.discussion_collaboration.runtime import DiscussionProject

with TemporaryDirectory(prefix="cooperative-tools-", dir=ROOT / "build") as directory:
    project = DiscussionProject(directory)
    try:
        node = project.backend.network.get("collab")
        old = node.modules.get("cooperation.group")
        current = project.make(old.module_id, old.config, dict(channels=old.channels, strength=old.strength, channel_mode=old.channel_mode))
        current.state = deepcopy(old.state)
        node.remove(old)
        node.install(current)
        record = next(row for row in project.saver.document(project.backend.network, directory)["nodes"] if row["node_id"] == node.info.node_id)
        file = ROOT / "projects/discussion_collaboration/nodes" / (sha256(node.info.node_id.encode()).hexdigest()[:24] + ".json")
        file.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Updated actual cooperative tools:", len(list(current.tools)))
    finally:
        project.close()
