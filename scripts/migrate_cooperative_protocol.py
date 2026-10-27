"""把实际讨论应用接入旧去中心化验收协议，只转换业务模块与配置。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from domain.core import Link, MarkdownNode, NodeInfo
from projects.discussion_collaboration.runtime import DiscussionProject
from projects.discussion_collaboration.modules.app_coordinator import AppCoordinatorModule


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    folder = ROOT / "projects/discussion_collaboration"
    manifest = json.loads((folder / "networks/main.json").read_text(encoding="utf-8"))
    metadata = json.loads((folder / "nexarbor.json").read_text(encoding="utf-8"))
    if "cooperation.group" in metadata["resources"]["modules"]:
        raise RuntimeError("项目已经完成协议转换")
    with TemporaryDirectory(prefix="cooperative-project-migration-", dir=ROOT / "build") as directory:
        project = DiscussionProject(directory)
        try:
            backend = project.backend
            group = backend.network.get("collab")
            for name in ("collab.participant", "collab.board.rev_9191e2380f.rev_96569f0263", "git.integrator.rev_2863bbe53e.rev_c376775a7e"):
                group.remove(name)
            for field in ("output", "findings"):
                relative = "data/collab/" + field + ".md"
                path = Path(directory) / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
                node_id = "collab/" + field
                document = MarkdownNode(NodeInfo(node_id, "协作交付" if field == "output" else "协作记录"), path)
                document.bias = -1
                backend.network.add(document)
                group.links.add(Link(node_id, "collaboration.delivery", threshold=1))
                (folder / relative).parent.mkdir(parents=True, exist_ok=True)
                (folder / relative).write_text("", encoding="utf-8")
                manifest["files"].append(relative)
                manifest["properties"][node_id] = dict(management_parent_id=None, offered_ports=[])
            group.links.add(Link("root", "collaboration.result", threshold=1))
            group.install(project.make("cooperation.group", dict(output="collab/output", findings="collab/findings"), dict(strength=2, channels=["collaboration"])))
            for index in range(1, 5):
                node = backend.network.get("executor-" + str(index))
                node.remove("agents.activity")
                node.install(project.make("cooperation.member", {}, dict(strength=2, channels=["collaboration"])))
                backend.bindings[node.info.node_id]["prepare"] = [dict(module="cooperation.member", operation="prepare", arguments={}, channels=[])]
            root = backend.network.get("root")
            previous = root.modules.get("app.coordinator.entry")
            config = deepcopy(previous.config)
            config["cooperative_module"] = "cooperation.group"
            root.remove(previous)
            root.install(AppCoordinatorModule(project.emit, config, strength=previous.strength, channels=previous.channels))
            records = project.saver.document(backend.network, directory)["nodes"]
            for record in records:
                if record["node_id"] in backend.bindings:
                    record["execution"] = deepcopy(backend.bindings[record["node_id"]])
                file = "nodes/" + sha256(record["node_id"].encode()).hexdigest()[:24] + ".json"
                write(folder / file, record)
            manifest["nodes"] = [dict(file="nodes/" + sha256(record["node_id"].encode()).hexdigest()[:24] + ".json") for record in records]
        finally:
            project.close()
    for name in ("collab.participant", "collab.board.rev_9191e2380f.rev_96569f0263", "git.integrator.rev_2863bbe53e.rev_c376775a7e"):
        metadata["resources"]["modules"].pop(name)
    for name, directory in (("cooperation.group", "cooperative_group"), ("cooperation.member", "cooperative_member")):
        metadata["resources"]["modules"][name] = dict(folder="modules/" + directory)
    path = folder / "modules/app_coordinator/module.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec["config_schema"]["properties"]["cooperative_module"] = dict(type="string")
    spec["description"] = "启动讨论并交接执行组；成员提出候选、全员验收后自动交付并同步运行状态。"
    for field in ("operations", "agent_tools"):
        spec[field] = [item for item in spec[field] if item.get("operation", item.get("name")) not in ("integrate", "promote")]
    write(path, spec)
    write(folder / "networks/main.json", manifest)
    write(folder / "nexarbor.json", metadata)
    print(json.dumps(dict(nodes=len(records), protocol="propose/approve/reject", core_changes=False)))


if __name__ == "__main__":
    main()
