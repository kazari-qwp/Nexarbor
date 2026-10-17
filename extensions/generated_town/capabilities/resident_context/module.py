"""居民上下文准备：在每次模型请求前刷新 Agent 的四路输入，不启动 Agent。"""
import json
from pathlib import Path

from datanet.studio.contract import StudioModule

SOURCE = 'resident.context'
OPENING_ID = 'opening'


def _text(value):
    """把任意 JSON 资料值转成可放进提示的文本。"""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Module(StudioModule):
    def setup(self):
        self.state.setdefault('opening_delivered', False)

    # ---------- 读取配置与外部输入 ----------

    def _component(self, key, default):
        value = self.config.get(key, default)
        if not isinstance(value, str) or not value:
            raise ValueError(f'配置 {key} 必须是非空组件 ID')
        return value

    def _channels(self, key):
        values = self.config[key]
        if not isinstance(values, list) or not values:
            raise ValueError(f'配置 {key} 必须是非空频道数组')
        return set(values)

    def _read_text(self, key, label):
        relative = self.config[key]
        root = Path(self.backend.directory).resolve()
        candidate = Path(relative)
        if candidate.is_absolute():
            raise ValueError(f'{label}文件必须是 backend.directory 下的相对路径：{relative}')
        target = (root / candidate).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f'{label}文件不能离开 backend.directory：{relative}')
        try:
            return target.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError) as error:
            raise ValueError(f'{label}文件读取失败：{relative}（{error}）') from error

    def _call(self, node_id, component, operation, label):
        try:
            return self.backend.modules.call(node_id, component, operation, {})
        except Exception as error:
            raise ValueError(
                f'{label}不可用（节点 {node_id}，组件 {component}）：{error}'
            ) from error

    # ---------- 现场连接 ----------

    def _related(self, place, channels):
        """只依据当前真实连接，同时看场所的出边与指向场所的入边。"""
        found = []
        for edge in place.interfaces:
            if channels.intersection(edge.metadata.channels):
                found.append(edge.target_node_id)
        for node in self.backend.network.nodes.values():
            if node.node_id == place.node_id:
                continue
            for edge in node.interfaces:
                if edge.target_node_id == place.node_id and channels.intersection(edge.metadata.channels):
                    found.append(node.node_id)
                    break
        return found

    def _person(self, node):
        """同场人物只公开姓名、性别、职业。"""
        profile = {}
        try:
            snapshot = self.backend.modules.call(node.node_id, self._component('entity_component', 'entity.profile'), 'read', {})
            if isinstance(snapshot, dict) and isinstance(snapshot.get('profile'), dict):
                profile = snapshot['profile']
        except Exception:
            profile = {}
        name = profile.get('name')
        if not isinstance(name, str) or not name:
            name = node.name
        gender = profile.get('gender')
        occupation = profile.get('occupation')
        return dict(
            node_id=node.node_id,
            name=name,
            gender=gender if isinstance(gender, str) and gender else '未知',
            occupation=occupation if isinstance(occupation, str) and occupation else '未知',
        )

    def _clock_text(self, clock):
        if not isinstance(clock, dict):
            return '尚未开始'
        text = clock.get('text')
        if isinstance(text, str) and text:
            return text
        day, slot = clock.get('day'), clock.get('slot')
        if isinstance(day, int) and day >= 1:
            return f'第{day}天-{slot}' if isinstance(slot, str) and slot else f'第{day}天'
        return '尚未开始'

    # ---------- 内部操作 ----------

    def prepare(self):
        if not hasattr(self.node, 'inputs'):
            raise ValueError('居民上下文组件只能挂载在 Agent 节点上')

        # 先读完所有外部输入，任何一项失败都不改动输入面和开场白标记。
        persona = self._read_text('persona_file', '人格')
        common = self._read_text('common_sense_file', '常识')
        map_text = self._read_text('map_file', '地图')

        entity_component = self._component('entity_component', 'entity.profile')
        action_component = self._component('action_component', 'action.points')
        clock_component = self._component('clock_component', 'time.text')

        snapshot = self._call(self.node.node_id, entity_component, 'read', '实体资料组件')
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('profile'), dict):
            raise ValueError('实体资料组件返回的 profile 不是对象')
        profile = snapshot['profile']
        coins = snapshot.get('coins', 0)
        items = snapshot.get('items') if isinstance(snapshot.get('items'), dict) else {}

        balance = self._call(self.node.node_id, action_component, 'get_balance', '行动值组件')
        if not isinstance(balance, dict):
            raise ValueError('行动值组件返回的余额不是对象')
        remaining = balance.get('remaining', '?')
        maximum = balance.get('max', '?')

        clock_node = self.config['clock_node']
        if not isinstance(clock_node, str) or not clock_node:
            raise ValueError('配置 clock_node 必须是非空节点 ID')
        clock = self._call(clock_node, clock_component, 'get_time', '时钟组件')

        place_id = profile.get('place')
        if not isinstance(place_id, str) or not place_id:
            raise ValueError('实体资料缺少 profile.place，无法确定当前地点')
        place = self.backend.network.nodes.get(place_id)
        if place is None:
            raise ValueError(f'profile.place 指向的节点不存在：{place_id}')

        presence_channels = self._channels('presence_channels')
        road_channels = self._channels('road_channels')

        people = []
        seen_people = set()
        for target_id in self._related(place, presence_channels):
            if target_id in seen_people or target_id == self.node.node_id:
                continue
            target = self.backend.network.nodes.get(target_id)
            if target is None or target.signal_type != 'agent':
                continue
            seen_people.add(target_id)
            people.append(self._person(target))
        people.sort(key=lambda person: (person['name'], person['node_id']))

        adjacent = []
        seen_places = set()
        for target_id in self._related(place, road_channels):
            if target_id in seen_places or target_id == place.node_id:
                continue
            target = self.backend.network.nodes.get(target_id)
            if target is None or target.signal_type == 'agent':
                continue
            seen_places.add(target_id)
            adjacent.append(target.name or target.node_id)
        adjacent.sort()

        # 自身资料不含 place：当前地点由“本地场所”单独表达。
        fields = {key: value for key, value in profile.items() if key != 'place'}
        profile_text = '；'.join(f'{key}={_text(value)}' for key, value in sorted(fields.items())) or '无'
        item_text = '、'.join(f'{name}×{count}' for name, count in sorted(items.items())) or '无'
        place_name = place.name or place.node_id
        place_text = f'本地场所：{place_name}'
        if isinstance(place.description, str) and place.description.strip():
            place_text += f'（{place.description.strip()}）'

        tail = [
            f'当前时间：{self._clock_text(clock)}',
            f'自身资料：{profile_text}',
            f'金币：{_text(coins)}',
            f'物品：{item_text}',
            f'行动余额：{_text(remaining)}/{_text(maximum)}',
            place_text,
            '同场人物：' + ('；'.join(
                f"{person['name']}（{person['gender']}，{person['occupation']}）" for person in people
            ) or '无'),
            '相邻地点：' + ('、'.join(adjacent) or '无'),
        ]

        system_prompt = '\n\n'.join(part for part in (persona.strip(), common.strip()) if part)

        patch = dict(
            system_prompt=system_prompt,
            context=[dict(id='map', text=map_text)],
            tail=tail,
        )
        deliver_opening = not self.state.get('opening_delivered', False)
        opening_line = self.config['opening_line']
        if deliver_opening and opening_line:
            patch['inputs'] = [dict(id=OPENING_ID, text=opening_line)]

        self.node.inputs.update(SOURCE, patch)
        if deliver_opening:
            self.state['opening_delivered'] = True

        return dict(
            prepared=True,
            opening_delivered=self.state['opening_delivered'],
            delivered_opening=bool(deliver_opening and opening_line),
            place=place.node_id,
            people=[person['name'] for person in people],
            adjacent=adjacent,
        )
