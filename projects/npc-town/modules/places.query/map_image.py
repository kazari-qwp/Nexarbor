"""把已授权的地点/道路绘为可缓存的 PNG；不计算路线。"""
import base64
import io
import json
import math
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=12)
def _font(size):
    from PIL import ImageFont
    candidates = (Path('C:/Windows/Fonts/msyh.ttc'), Path('C:/Windows/Fonts/simhei.ttf'),
                  Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'), Path('/System/Library/Fonts/PingFang.ttc'))
    for file in candidates:
        if file.is_file():
            return ImageFont.truetype(str(file), size)
    raise RuntimeError('地图绘制需要中文字体，请安装微软雅黑或 Noto Sans CJK')


def _positions(points, roads, layout):
    configured = {item['node']: (item['x'], item['y']) for item in layout}
    keys = [item['id'] for item in points]
    if all(key in configured for key in keys):
        return {key: configured[key] for key in keys}
    # 无手工布局时使用稳定的力导向布局；节点按 ID 排序，重复查询不会随机重排。
    count = len(keys)
    positions = {key: [0.5 + 0.4 * math.cos(2 * math.pi * i / max(1, count)), 0.5 + 0.4 * math.sin(2 * math.pi * i / max(1, count))] for i, key in enumerate(keys)}
    ideal = 0.75 / math.sqrt(max(1, count))
    for step in range(180):
        forces = {key: [0.0, 0.0] for key in keys}
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                dx, dy = positions[a][0] - positions[b][0], positions[a][1] - positions[b][1]
                distance = max(0.001, math.hypot(dx, dy))
                force = ideal * ideal / distance
                for axis, delta in enumerate((dx, dy)):
                    change = delta / distance * force
                    forces[a][axis] += change
                    forces[b][axis] -= change
        for edge in roads:
            a, b = edge['from'], edge['to']
            dx, dy = positions[a][0] - positions[b][0], positions[a][1] - positions[b][1]
            distance = max(0.001, math.hypot(dx, dy))
            force = distance * distance / ideal
            for axis, delta in enumerate((dx, dy)):
                change = delta / distance * force
                forces[a][axis] -= change
                forces[b][axis] += change
        temperature = 0.04 * (1 - step / 180)
        for key in keys:
            length = max(0.001, math.hypot(*forces[key]))
            for axis in (0, 1):
                positions[key][axis] = max(0.04, min(0.96, positions[key][axis] + forces[key][axis] / length * min(length, temperature)))
    return positions


@lru_cache(maxsize=8)
def _render(serialized, title, layout_json):
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise RuntimeError('查询地图需要 Pillow，请安装该模块 requirements.txt 中的依赖') from error
    graph = json.loads(serialized)
    points, roads = graph['places'], graph['roads']
    width, height = 1280, 920
    if len(points) > 20:
        width, height = 1920, 1440
    image = Image.new('RGB', (width, height), '#f6f7f5')
    draw = ImageDraw.Draw(image)
    positions = {key: (110 + value[0] * (width - 220), 190 + value[1] * (height - 310)) for key, value in _positions(points, roads, json.loads(layout_json)).items()}
    draw.text((60, 45), title[:40], font=_font(32), fill='#22352e')
    draw.text((60, 100), '线段为道路；箭头表示单向通行。位置为示意，不表示实际距离。', font=_font(18), fill='#617167')
    radius = 65 if len(points) <= 12 else 48
    for edge in roads:
        a, b = positions[edge['from']], positions[edge['to']]
        draw.line([a, b], fill='#88998e', width=4)
        if not edge['bidirectional']:
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = max(1, math.hypot(dx, dy))
            ux, uy = dx / length, dy / length
            tip = b[0] - ux * (radius + 5), b[1] - uy * (radius + 5)
            draw.polygon([tip, (tip[0] - 17 * ux + 8 * uy, tip[1] - 17 * uy - 8 * ux), (tip[0] - 17 * ux - 8 * uy, tip[1] - 17 * uy + 8 * ux)], fill='#52755e')
    for item in points:
        x, y = positions[item['id']]
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill='#ffffff', outline='#52755e', width=3)
        label = item['name']
        size = 24 if len(label) <= 4 else 19
        lines = [label[i:i + 6] for i in range(0, min(len(label), 18), 6)]
        caption = item.get('description', '').split('。')[0]
        if len(lines) == 1 and caption and len(caption) <= 7:
            draw.text((x, y - 12), label, font=_font(size), fill='#22352e', anchor='mm')
            draw.text((x, y + 23), caption, font=_font(16), fill='#617167', anchor='mm')
        else:
            for i, line in enumerate(lines):
                draw.text((x, y + (i - (len(lines) - 1) / 2) * 25), line, font=_font(size), fill='#22352e', anchor='mm')
    draw.text((60, height - 50), f'{len(points)} 个地点 · {len(roads)} 条道路', font=_font(18), fill='#617167')
    output = io.BytesIO()
    image.save(output, format='PNG', optimize=True)
    return base64.b64encode(output.getvalue()).decode('ascii')


def render_map(graph, config):
    return _render(json.dumps(graph, ensure_ascii=False, sort_keys=True), config.get('map_title', '地点道路图'), json.dumps(config.get('map_layout', []), ensure_ascii=False, default=list))
