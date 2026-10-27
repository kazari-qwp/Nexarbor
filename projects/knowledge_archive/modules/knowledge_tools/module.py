"""原知识工具映射、只读任务约束和入库流程；跨节点操作统一经 access。"""
from copy import deepcopy
from hashlib import sha256
import csv
import json
from pathlib import Path
from domain.core import CallableTool, Module, access
from domain.json_values import thaw
from ..knowledge_catalog.access import CatalogAccess

TOOLS = json.loads(Path(__file__).with_name("tools.json").read_text(encoding="utf-8"))


class KnowledgeToolsModule(Module):
    def __init__(self, directory, config=None, state=None, **access_settings):
        super().__init__("knowledge.tools", **access_settings)
        self.directory = Path(directory).resolve()
        self.config, self.state = deepcopy(config or {}), deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec["id"], getattr(self, spec["operation"]), spec["description"], deepcopy(spec["parameters"])))

    def _bind(self, node):
        super()._bind(node)
        source = sha256((node.info.node_id + "\0" + self.module_id).encode()).hexdigest()[:24]
        for tool, spec in zip(self.tools, TOOLS):
            tool.name = "mod_" + sha256((source + "\0" + spec["id"]).encode()).hexdigest()[:24]
            tool.description = node.info.node_id + " · " + spec["name"] + " · " + spec["description"]

    @access(channels=["knowledge"])
    async def _collections(self, node):
        collection = node.modules.get("knowledge.collection")
        if collection is not None:
            return collection.config["collection"]

    @access(channels=["knowledge"])
    async def _collection(self, node, target, operation, parameters):
        if node.info.node_id == target:
            return await node.modules.get("knowledge.collection").execute(operation, **parameters)

    async def storage(self, operation, parameters=None):
        parameters = dict(parameters or {})
        catalog = CatalogAccess(self)
        if operation in ("catalog", "create_collection", "stage", "intake", "route", "guide", "pending", "finish_intake"):
            return await catalog.call(operation, parameters)
        if operation == "search" and not parameters.get("collection"):
            visible = [value for value in (await self._collections()).values() if value is not None]
            return await catalog.call("search", dict(parameters, allowed_collections=visible))
        descriptor = await catalog.call("collection", {"target": parameters["collection"]}) if parameters.get("collection") else await catalog.call("locate", {"id": parameters["id"]})
        return (await self._collection(descriptor["node_id"], operation, parameters))[descriptor["node_id"]]

    async def docs(self, node, operation, parameters=None):
        return await getattr(node.modules.get("documents.tasks"), operation)(**(parameters or {}))

    async def guide(self, node, name):
        item = await self.storage("guide", dict(name=name))
        node.update_inputs(self.module_id, context=[item])

    async def ingest(self, node, p):
        if p.get('intake_id'):item=await self.storage('intake',dict(id=p['intake_id']))
        else:
            content=p.get('content');source=None
            if p.get('file_path'):
                workspace=self.directory/'workspace';source=Path(p['file_path']);source=(source if source.is_absolute() else workspace/source).resolve()
                if not source.is_relative_to(workspace.resolve()):raise ValueError('Import file must be inside the application workspace')
                if source.suffix.lower()=='.csv':
                    with source.open(encoding='utf-8-sig',newline='') as file:content=list(csv.DictReader(file))
                elif source.suffix.lower()=='.json':content=json.loads(source.read_text('utf8'))
                elif source.suffix.lower() in ('.md','.txt'):content=source.read_text('utf8')
                else:raise ValueError('Supported import files: CSV, JSON, TXT, Markdown')
            if content is None:raise ValueError('Provide content, file_path or an existing intake_id')
            item=await self.storage('stage',dict(content=content,purpose=p.get('purpose',''),original_file=str(source) if source else None))
        task=await self.docs(node,'current')
        if task and task['mode']=='read':raise ValueError('Current task is read-only')
        if not task:await self.docs(node,'begin',dict(content={'intake_id':item['id'],'purpose':item['purpose']},mode='write'))
        reference=await self.docs(node,'reference',dict(intake_id=item['id']))
        target=p.get('collection') or (await self.storage('route',dict(id=item['id'])))['collection']
        if item['status']=='completed':result=item['result']
        elif target:result=await self.storage('commit_intake',dict(id=item['id'],collection=target))
        else:return dict(status='pending',intake_id=item['id'],**reference)
        await self.docs(node,'remember',dict(records=result.get('records',[])))
        await self.docs(node,'task_document_write',dict(content=json.dumps(result,ensure_ascii=False),receipts=result.get('records',[])))
        return dict(**result,**reference)

    async def kb_catalog(self, **parameters):
        return await self.execute("kb_catalog", **parameters)

    async def kb_create_node(self, **parameters):
        return await self.execute("kb_create_node", **parameters)

    async def kb_store(self, **parameters):
        return await self.execute("kb_store", **parameters)

    async def kb_fetch(self, **parameters):
        return await self.execute("kb_fetch", **parameters)

    async def kb_search(self, **parameters):
        return await self.execute("kb_search", **parameters)

    async def kb_update(self, **parameters):
        return await self.execute("kb_update", **parameters)

    async def kb_delete(self, **parameters):
        return await self.execute("kb_delete", **parameters)

    async def kb_export(self, **parameters):
        return await self.execute("kb_export", **parameters)

    async def kb_intake(self, **parameters):
        return await self.execute("kb_intake", **parameters)

    async def kb_index(self, **parameters):
        return await self.execute("kb_index", **parameters)

    async def kb_query(self, **parameters):
        return await self.execute("kb_query", **parameters)

    async def kb_wiki(self, **parameters):
        return await self.execute("kb_wiki", **parameters)

    async def kb_ingest(self, **parameters):
        return await self.execute("kb_ingest", **parameters)

    async def kb_task(self, **parameters):
        return await self.execute("kb_task", **parameters)

    async def prepare(self, **parameters):
        return await self.execute("prepare", **parameters)

    async def execute(self, operation, **parameters):
        return next(iter((await self._operate(operation, parameters)).values()))

    @access(channels=())
    async def _operate(self, node, op, p):
        p = thaw(p)
        if op=='prepare':
            task=await self.docs(node,'current');tail=[] if not task else [f"[当前知识任务] {task['id']}；模式：{task['mode']}。只读任务不修改知识记录，交付文档仍可写入。"]
            return dict(format='nexarbor-context/v1',patch=dict(system_prompt='',context=[],inputs=[],tail=tail),sources=[],errors=[])
        await self.guide(node,'AGENTS.md')
        task=await self.docs(node,'current')
        if op=='kb_task':
            ref=await self.docs(node,'begin',dict(content=p['content'],mode=p.get('mode','agent')))
            return await self.ingest(node,dict(content=p['content'])) if p.get('mode')=='write' else ref
        mutations={'kb_ingest','kb_create_node','kb_store','kb_update','kb_delete','kb_index'}
        if op in mutations and task and task['mode']=='read':raise ValueError('Current task is read-only')
        if op=='kb_intake' and p.get('action','read')!='read':
            if task and task['mode']=='read':raise ValueError('Current task is read-only')
            if p.get('record_id'):await self.storage('fetch',dict(id=p['record_id']))
            return await self.storage('finish_intake',p)
        if op=='kb_ingest':return await self.ingest(node,p)
        if op=='kb_wiki':
            workflow=p.get('workflow','query' if p.get('action')=='search' else 'lint' if p.get('action')=='lint' else 'ingest')
            await self.guide(node,'WIKI.md');await self.guide(node,workflow)
            result=await self.storage('wiki',p)
        elif op=='kb_store':
            if p.get('intake_id'):result=await self.storage('commit_intake',dict(id=p['intake_id'],collection=p['collection'],**({'indices':p['indices']} if 'indices' in p else {})))
            else:
                p.pop('intake_id',None);p['value']=p.pop('content');result=await self.storage('store',p)
        else:
            mapping={'kb_catalog':'catalog','kb_create_node':'create_collection','kb_fetch':'fetch','kb_search':'search','kb_update':'update','kb_delete':'delete','kb_export':'export','kb_intake':'intake','kb_index':'index','kb_query':'query'}
            if op=='kb_intake' and not p.get('id'):return await self.storage('pending',p)
            if op=='kb_intake':p.pop('action',None);p['preview']=True
            result=await self.storage(mapping[op],p)
        if op in ('kb_store','kb_update'):
            records=result.get('records',[result] if 'id' in result and 'version' in result else [])
            await self.docs(node,'remember',dict(records=records))
        return result
