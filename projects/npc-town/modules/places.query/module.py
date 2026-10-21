"""地理工具的显式读取。发布公开资料也是明确的准备操作，与上下文装配无关。"""
from datanet.core.module_protocol import ComponentResult
from .scene import scene, inspect_place, map_graph, call, plain as _plain
from .map_image import render_map
def _error(message): return ComponentResult(status='error', error=message)
async def execute(ctx, activation):
    if ctx.requester_id != ctx.node_id: return _error('只能查询自己的处境')
    operation, parameters = activation.operation, activation.parameters or {}
    if operation == 'publish':
        values = (await call(ctx, ctx.node_id, 'records.store', 'read')).get('values', {})
        fields = {k: _plain(values[k]) for k in ctx.config.get('public_fields', ('name', 'gender', 'profession', 'age_group')) if k in values}
        ctx.publish_metadata(fields)
        return ComponentResult(data=fields)
    if operation == "look":
        try:
            return ComponentResult(data=await scene(ctx))
        except RuntimeError as exc:
            return _error(str(exc))

    if operation == "place":
        try:
            return ComponentResult(data=await inspect_place(ctx, parameters.get("place")))
        except (RuntimeError, ValueError) as exc:
            return _error(str(exc))

    if operation == "map":
        try:
            graph = await map_graph(ctx)
            if not graph["places"]:
                return _error("当前授权范围内没有可绘制的地点")
            image = render_map(graph, _plain(ctx.config))
            labels = "；".join(item["name"] + "=" + item["id"] for item in graph["places"])
            return ComponentResult(data={"format": "nexarbor-tool-content/v1", "content": [
                {"type": "text", "text": "地点道路图。线段为道路，箭头为单向通行；示意位置不代表距离。地点编号：" + labels},
                {"type": "image", "name": "地点道路图.png", "mediaType": "image/png", "data": image}]})
        except (RuntimeError, ValueError) as exc:
            return _error(str(exc))

    return _error('不支持的操作')
