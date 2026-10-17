"""可配置的家庭业务：民政登记、家庭计划、医院接生。

所有实体节点、地点、时钟与依赖组件都来自实例配置；人物资料存放在
``entity.profile`` 的 ``profile`` 中，调用者身份来自 ``current_agent_id()``。
"""

from pathlib import Path

from datanet.core.access_budget import current_agent_id
from datanet.core.agent_node import AgentNode
from datanet.studio.contract import StudioModule

MODE_TOOLS = {
    'civil': 'register_marriage',
    'family': 'plan_child',
    'hospital': 'give_birth',
}


def _plain(value):
    """把冻结的配置值还原成普通可修改的 JSON 数据。"""
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _pair_key(first, second):
    return '\x1f'.join(sorted((first, second)))


class Module(StudioModule):

    # ------------------------------------------------------------------ 生命周期
    def setup(self):
        self.state.setdefault('marriage_consents', {})
        self.state.setdefault('family_consents', {})
        if self.config.get('mode') == 'hospital':
            template = self.config.get('child_template') or {}
            modules = template.get('modules')
            entity = self.config.get('entity_component')
            if not isinstance(modules, dict) or entity not in modules:
                raise ValueError('医院模式需要在 child_template.modules 中提供 ' + str(entity) + ' 的配置')
            memory = template.get('memory_path')
            if not isinstance(memory, str) or ('{node_id}' not in memory and '{name}' not in memory):
                raise ValueError('child_template.memory_path 必须包含 {node_id} 或 {name} 占位符，保证每个孩子记忆独立')
            try:
                memory.format(node_id='child/示例', name='示例')
            except Exception as error:
                raise ValueError('child_template.memory_path 只能使用 {node_id} 与 {name} 占位符：' + str(error))

    def tool_enabled(self, name):
        return MODE_TOOLS.get(self.config.get('mode')) == name

    def tool_description(self, name, default):
        if not self.tool_enabled(name):
            return default
        place = self.config.get('place')
        label = self._place_name(place)
        cost = self._cost(name)
        return default + f'（地点：{label}；每次花费 {cost} 点行动值）'

    # ------------------------------------------------------------------ 民政登记
    def register_marriage(self, partner):
        caller = current_agent_id()
        problem = self._caller_problem(caller)
        if problem is not None:
            return problem
        if not isinstance(partner, str) or not partner.strip():
            return self._reject('invalid_partner', '对方节点 ID 必须是非空字符串，本次未登记。')
        partner = partner.strip()
        if partner == caller:
            return self._reject('same_person', '不能与自己登记结婚，本次未登记。')
        nodes = self.backend.network.nodes
        if partner not in nodes:
            return self._reject('unknown_partner', f'找不到对方节点「{partner}」，本次未登记。')

        caller_profile = self._profile(caller)
        partner_profile = self._profile(partner)
        if caller_profile is None or partner_profile is None:
            return self._reject('profile_unavailable', '无法读取双方的实体资料，本次未登记。')

        caller_spouse = caller_profile.get('spouse')
        partner_spouse = partner_profile.get('spouse')
        if caller_spouse or partner_spouse:
            if caller_spouse == partner and partner_spouse == caller:
                return {
                    'ok': True,
                    'registered': True,
                    'already': True,
                    'waiting': False,
                    'couple': [caller, partner],
                    'charged': 0,
                    'remaining': self._balance(caller),
                    'message': '你们已经是配偶，无需重复登记，也未扣除行动值。',
                }
            return self._reject('spouse_conflict', '其中一方已有配偶或双方配偶记录不一致，不能登记。')

        if not self._is_adult(caller_profile) or not self._is_adult(partner_profile):
            return self._reject('not_adult', '双方必须都是成年人才能登记结婚。')

        place = self.config.get('place')
        if place not in nodes:
            return self._reject('place_missing', f'登记处节点「{place}」不存在，本次未登记。')
        if caller_profile.get('place') != place or partner_profile.get('place') != place:
            return self._reject(
                'wrong_place',
                f'双方必须都在登记处「{self._place_name(place)}」才能登记，本次未登记。',
            )
        if not self._present(caller, place) or not self._present(partner, place):
            return self._reject(
                'not_present',
                f'双方必须与登记处「{self._place_name(place)}」保持双向在场连接'
                f'（{self.config.get("presence_channel")}），本次未登记。',
            )

        consents = self.state['marriage_consents']
        key = _pair_key(caller, partner)
        waiting = list(consents.get(key, []))
        cost = self._cost('register_marriage')
        if caller in waiting:
            return {
                'ok': True,
                'registered': False,
                'waiting': True,
                'already': False,
                'partner': partner,
                'charged': 0,
                'remaining': self._balance(caller),
                'message': '你已经同意过这门婚事，正在等对方亲自调用同一工具同意；本次未重复扣费。',
            }

        partner_waiting = partner in waiting
        with self.backend.modules.transaction(caller, partner, self.node.node_id):
            spent = self._spend(caller, cost)
            if not spent.get('ok'):
                return self._insufficient(cost, spent)
            if partner_waiting:
                self._update_profile(caller, {'spouse': partner})
                self._update_profile(partner, {'spouse': caller})
                consents.pop(key, None)
                return {
                    'ok': True,
                    'registered': True,
                    'already': False,
                    'waiting': False,
                    'couple': [caller, partner],
                    'charged': cost,
                    'remaining': spent.get('remaining'),
                    'message': '双方已各自同意，登记完成，你们的资料已互指为配偶。',
                }
            self._record_consent(consents, caller, key)
        return {
            'ok': True,
            'registered': False,
            'waiting': True,
            'already': False,
            'partner': partner,
            'charged': cost,
            'remaining': spent.get('remaining'),
            'message': f'已记录你对「{nodes[partner].name}」的结婚同意；请对方亲自调用 register_marriage 同意，才会完成登记。',
        }

    # ------------------------------------------------------------------ 家庭计划
    def plan_child(self):
        caller = current_agent_id()
        problem = self._caller_problem(caller)
        if problem is not None:
            return problem
        nodes = self.backend.network.nodes
        caller_profile = self._profile(caller)
        if caller_profile is None:
            return self._reject('profile_unavailable', '无法读取你的实体资料，本次未记录。')
        spouse = caller_profile.get('spouse')
        if not isinstance(spouse, str) or not spouse:
            return self._reject('not_married', '你还没有配偶记录，不能开始家庭计划。')
        if spouse not in nodes:
            return self._reject('spouse_missing', f'找不到配偶节点「{spouse}」，本次未记录。')
        spouse_profile = self._profile(spouse)
        if spouse_profile is None:
            return self._reject('profile_unavailable', '无法读取配偶的实体资料，本次未记录。')
        if spouse_profile.get('spouse') != caller:
            return self._reject('not_married', '双方的配偶记录没有互指，不能开始家庭计划。')

        place = self.config.get('place')
        if place not in nodes:
            return self._reject('place_missing', f'家庭地点节点「{place}」不存在，本次未记录。')
        if caller_profile.get('place') != place or spouse_profile.get('place') != place:
            return self._reject(
                'wrong_place',
                f'夫妻双方必须都在自己家「{self._place_name(place)}」才能要孩子，本次未记录。',
            )
        if caller_profile.get('home') != place or spouse_profile.get('home') != place:
            return self._reject(
                'wrong_home',
                f'夫妻双方必须都把「{self._place_name(place)}」登记为自己的家（profile.home），本次未记录。',
            )
        if not self._present(caller, place) or not self._present(spouse, place):
            return self._reject(
                'not_present',
                f'夫妻双方必须与家「{self._place_name(place)}」保持双向在场连接'
                f'（{self.config.get("presence_channel")}），本次未记录。',
            )
        if self._children(caller_profile) or self._children(spouse_profile):
            return self._reject('already_has_child', '这对夫妻已经有孩子，每对最多一个孩子，本次未记录。')
        if caller_profile.get('due_tick') is not None or spouse_profile.get('due_tick') is not None:
            return self._reject('already_planned', '这对夫妻已经有待产记录，每对最多一个孩子，本次未记录。')

        female = None
        if caller_profile.get('gender') == 'female':
            female = caller
        elif spouse_profile.get('gender') == 'female':
            female = spouse
        if female is None:
            return self._reject('no_female', '双方资料中都没有 gender=female 的角色，无法记录预产期。')

        tick = self._tick()
        if tick is None or tick < 0:
            return self._reject('clock_unavailable', '时钟尚未开始或无法读取当前时刻，本次未记录。')

        due_ticks = self.config.get('due_ticks', 10)
        cost = self._cost('plan_child')
        consents = self.state['family_consents']
        key = _pair_key(caller, spouse)
        waiting = list(consents.get(key, []))
        if caller in waiting:
            return {
                'ok': True,
                'planned': False,
                'waiting': True,
                'already': False,
                'partner': spouse,
                'charged': 0,
                'remaining': self._balance(caller),
                'message': '你已经同意要孩子，正在等配偶亲自调用同一工具同意；本次未重复扣费。',
            }

        partner_waiting = spouse in waiting
        due_tick = tick + due_ticks
        with self.backend.modules.transaction(caller, spouse, self.node.node_id):
            spent = self._spend(caller, cost)
            if not spent.get('ok'):
                return self._insufficient(cost, spent)
            if partner_waiting:
                self._update_profile(female, {'due_tick': due_tick})
                consents.pop(key, None)
                return {
                    'ok': True,
                    'planned': True,
                    'waiting': False,
                    'already': False,
                    'partner': spouse,
                    'mother': female,
                    'due_tick': due_tick,
                    'due_day': self._due_day(due_tick),
                    'charged': cost,
                    'remaining': spent.get('remaining'),
                    'message': self._due_message(due_tick, due_ticks),
                }
            self._record_consent(consents, caller, key)
        return {
            'ok': True,
            'planned': False,
            'waiting': True,
            'already': False,
            'partner': spouse,
            'charged': cost,
            'remaining': spent.get('remaining'),
            'message': '已记录你要孩子的同意；请配偶亲自调用 plan_child 同意，才会记录预产期。',
        }

    # ------------------------------------------------------------------ 医院接生
    def give_birth(self, name, gender):
        caller = current_agent_id()
        problem = self._caller_problem(caller)
        if problem is not None:
            return problem
        clean_name, clean_gender, invalid = self._child_arguments(name, gender)
        if invalid is not None:
            return invalid
        nodes = self.backend.network.nodes
        caller_profile = self._profile(caller)
        if caller_profile is None:
            return self._reject('profile_unavailable', '无法读取你的实体资料，本次未接生。')

        born = self._children(caller_profile)
        if born:
            existing = next((item for item in born if item in nodes), None)
            if existing is not None:
                return {
                    'ok': True,
                    'created': False,
                    'already': True,
                    'child': existing,
                    'child_name': nodes[existing].name,
                    'charged': 0,
                    'remaining': self._balance(caller),
                    'message': f'你已经有孩子「{nodes[existing].name}」，本次不重复创建，也未扣除行动值。',
                }
            return self._reject('child_missing', '资料显示你已生产，但记录中的孩子节点不存在；请人工检查后再试。')

        due_tick = caller_profile.get('due_tick')
        if due_tick is None:
            return self._reject('no_due', '你没有待产记录（profile.due_tick），本次未接生。')
        spouse = caller_profile.get('spouse')
        if not isinstance(spouse, str) or not spouse or spouse not in nodes:
            return self._reject('no_spouse', '没有可用的配偶节点，无法登记父母关系，本次未接生。')
        spouse_profile = self._profile(spouse)
        if spouse_profile is None or spouse_profile.get('spouse') != caller:
            return self._reject('not_married', '双方的配偶记录没有互指，无法登记父母关系，本次未接生。')

        tick = self._tick()
        if tick is None:
            return self._reject('clock_unavailable', '无法读取当前时刻，本次未接生。')
        if tick < due_tick:
            return self._reject(
                'not_due',
                f'还没到预产时刻：当前 tick={tick}，预产 tick={due_tick}，本次未接生。',
            )

        place = self.config.get('place')
        if place not in nodes:
            return self._reject('place_missing', f'医院节点「{place}」不存在，本次未接生。')
        if caller_profile.get('place') != place:
            return self._reject(
                'wrong_place',
                f'必须亲自在医院「{self._place_name(place)}」才能接生，本次未接生。',
            )
        if not self._present(caller, place):
            return self._reject(
                'not_present',
                f'你必须与医院「{self._place_name(place)}」保持双向在场连接'
                f'（{self.config.get("presence_channel")}），本次未接生。',
            )
        for key in ('time_node', 'save_node'):
            if self.config.get(key) not in nodes:
                return self._reject('wiring_missing', f'接线节点「{self.config.get(key)}」不存在，本次未接生。')
        management_parent = (self.config.get('child_template') or {}).get('management_parent_id')
        if management_parent is not None and management_parent not in nodes:
            return self._reject(
                'management_missing',
                f'child_template.management_parent_id「{management_parent}」不存在，本次未接生。',
            )

        cost = self._cost('give_birth')
        affordable = self._check(caller, cost)
        if affordable is not None and not affordable.get('ok'):
            return self._insufficient(cost, affordable)
        try:
            child_id, mounted, links, memory_path = self._create_child(
                caller, spouse, clean_name, clean_gender, place,
            )
        except Exception as error:  # 节点/文件/模块创建失败：明确拒绝，不扣行动值
            return self._reject('create_failed', f'创建孩子节点失败：{error}')

        spent_ok = False
        try:
            with self.backend.modules.transaction(caller, spouse, self.node.node_id):
                spent = self._spend(caller, cost)
                if spent.get('ok'):
                    self._register_birth(caller, spouse, caller_profile, spouse_profile, child_id)
                    spent_ok = True
        except Exception as error:
            self._discard_child(child_id, mounted, links, memory_path)
            return self._reject('birth_failed', f'接生登记失败：{error}')

        if not spent_ok:
            self._discard_child(child_id, mounted, links, memory_path)
            return self._insufficient(cost, spent)

        return {
            'ok': True,
            'created': True,
            'already': False,
            'child': child_id,
            'child_name': clean_name,
            'child_gender': clean_gender,
            'parents': [caller, spouse],
            'place': place,
            'charged': cost,
            'remaining': spent.get('remaining'),
            'message': f'孩子「{clean_name}」已在「{self._place_name(place)}」出生，父母关系已双向登记；孩子本轮不会启动，下一次脉冲会自然参加。',
        }

    # ------------------------------------------------------------------ 医院内部步骤
    def _create_child(self, caller, spouse, name, gender, place):
        template = self.config['child_template']
        modules = _plain(template.get('modules') or {})
        entity = self.config.get('entity_component')
        entity_config = modules.get(entity)
        if not isinstance(entity_config, dict):
            raise ValueError('child_template 缺少实体资料组件配置：' + str(entity))
        profile = _plain(entity_config.get('profile') or {})
        profile.update(_plain(template.get('profile') or {}))
        profile.update({
            'name': name,
            'gender': gender,
            'age_group': 'child',
            'parents': [caller, spouse],
            'place': place,
        })
        entity_config['profile'] = profile

        backend = self.backend
        directory = Path(backend.directory).resolve()
        prefix = self.config.get('child_id_prefix', 'child')
        child_id = None
        memory_path = None
        for index in range(1, 101):
            candidate = prefix + '/' + name if index == 1 else prefix + '/' + name + '-' + str(index)
            rendered = template['memory_path'].format(node_id=candidate, name=name)
            candidate_path = (directory / rendered).resolve()
            if not candidate_path.is_relative_to(directory):
                raise ValueError('child_template.memory_path 越出运行目录')
            if candidate not in backend.network.nodes and not candidate_path.exists():
                child_id, memory_path = candidate, candidate_path
                break
        if child_id is None:
            raise ValueError('找不到可用的孩子节点编号，请换一个名字')
        if child_id in backend.network.nodes:
            raise ValueError('孩子节点编号已存在：' + child_id)

        mounted = []
        links = []
        try:
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            memory_path.write_text(template.get('memory_text', ''), encoding='utf-8')
            child = AgentNode(
                child_id,
                name,
                file_path=memory_path,
                description=template.get('description', ''),
            )
            child.divergence = -1
            child.management_parent_id = template.get('management_parent_id')
            child.execution_binding = _plain(template.get('execution') or {})
            backend.network.add_node(child)
            for module_id, module_config in modules.items():
                backend.modules.mount(child_id, module_id, module_config, bind=False)
                mounted.append(module_id)
            time_node = backend.network.nodes[self.config['time_node']]
            save_node = backend.network.nodes[self.config['save_node']]
            place_node = backend.network.nodes[place]
            presence = self.config['presence_channel']
            links.append((time_node, time_node.connect(child_id, channels=['world.tick'], threshold=1)))
            links.append((child, child.connect(self.config['save_node'], channels=['world.tick'], threshold=1)))
            links.append((place_node, place_node.connect(child_id, channels=[presence], threshold=1)))
            links.append((child, child.connect(place, channels=[presence], threshold=1)))
            backend.modules.refresh()
        except Exception:
            self._discard_child(child_id, mounted, links, memory_path)
            raise
        return child_id, mounted, links, memory_path

    def _register_birth(self, caller, spouse, caller_profile, spouse_profile, child_id):
        caller_fields = {'children': self._with_child(caller_profile, child_id), 'due_tick': None}
        spouse_fields = {'children': self._with_child(spouse_profile, child_id)}
        self._update_profile(caller, caller_fields)
        self._update_profile(spouse, spouse_fields)

    def _discard_child(self, child_id, mounted, links, memory_path):
        for source, interface in reversed(links):
            try:
                if interface in source.interfaces:
                    source.interfaces.remove(interface)
            except Exception:
                pass
        for module_id in reversed(mounted):
            try:
                self.backend.modules.unmount(child_id, module_id)
            except Exception:
                pass
        try:
            self.backend.network.nodes.pop(child_id, None)
        except Exception:
            pass
        try:
            memory_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            self.backend.modules.refresh()
        except Exception:
            pass

    # ------------------------------------------------------------------ 通用工具
    def _caller_problem(self, caller):
        if not isinstance(caller, str) or not caller:
            return self._reject('no_caller', '无法确认调用者身份，本次操作未执行。')
        if caller not in self.backend.network.nodes:
            return self._reject('unknown_caller', f'调用者节点「{caller}」不存在，本次操作未执行。')
        return None

    def _child_arguments(self, name, gender):
        if not isinstance(name, str) or not name.strip():
            return None, None, self._reject('invalid_name', '孩子的姓名必须是非空字符串，本次未接生。')
        name = name.strip()
        if len(name) > 40 or any(char in name for char in '/\\\x00<>:"|?*'):
            return None, None, self._reject('invalid_name', '孩子姓名不能包含斜杠、文件名保留字符或控制字符，且不超过 40 个字符。')
        if not isinstance(gender, str) or not gender.strip():
            return None, None, self._reject('invalid_gender', '孩子的 gender 必须是非空字符串，本次未接生。')
        return name, gender.strip(), None

    def _profile(self, node_id):
        try:
            result = self.backend.modules.call(
                node_id, self.config.get('entity_component', 'entity.profile'), 'read', {},
            )
        except Exception:
            return None
        profile = result.get('profile') if isinstance(result, dict) else None
        return profile if isinstance(profile, dict) else None

    def _update_profile(self, node_id, fields):
        self.backend.modules.call(
            node_id, self.config.get('entity_component', 'entity.profile'), 'update_profile', {'fields': fields},
        )

    def _balance(self, node_id):
        try:
            result = self.backend.modules.call(
                node_id, self.config.get('action_component', 'action.points'), 'get_balance', {},
            )
        except Exception:
            return None
        return result.get('remaining') if isinstance(result, dict) else None

    def _spend(self, node_id, amount):
        try:
            result = self.backend.modules.call(
                node_id, self.config.get('action_component', 'action.points'), 'spend', {'amount': amount},
            )
        except Exception as error:
            return {'ok': False, 'reason': 'unavailable', 'message': str(error)}
        return result if isinstance(result, dict) else {'ok': False, 'reason': 'unavailable', 'message': '行动值组件返回异常'}

    def _check(self, node_id, amount):
        try:
            result = self.backend.modules.call(
                node_id, self.config.get('action_component', 'action.points'), 'check', {'amount': amount},
            )
        except Exception:
            return None
        return result if isinstance(result, dict) else None

    def _tick(self):
        try:
            result = self.backend.modules.call(
                self.config['clock_node'], self.config.get('clock_component', 'time.text'), 'get_tick', {},
            )
        except Exception:
            return None
        tick = result.get('tick') if isinstance(result, dict) else None
        return tick if isinstance(tick, int) and not isinstance(tick, bool) else None

    def _cost(self, tool):
        costs = self.config.get('costs') or {}
        value = costs.get(tool, 1)
        return value if isinstance(value, int) and not isinstance(value, bool) else 1

    def _is_adult(self, profile):
        if profile.get('age_group') in ('child', 'minor'):
            return False
        age = profile.get('age')
        return isinstance(age, (int, float)) and not isinstance(age, bool) and age >= self.config.get('adult_age', 18)

    def _children(self, profile):
        value = profile.get('children')
        return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []

    def _with_child(self, profile, child_id):
        children = self._children(profile)
        if child_id not in children:
            children.append(child_id)
        return children

    def _record_consent(self, consents, caller, key):
        for other_key in list(consents):
            if other_key == key:
                continue
            remaining = [item for item in consents[other_key] if item != caller]
            if remaining:
                consents[other_key] = remaining
            else:
                del consents[other_key]
        waiting = list(consents.get(key, []))
        if caller not in waiting:
            waiting.append(caller)
        consents[key] = waiting

    def _due_day(self, due_tick):
        per_day = self.config.get('ticks_per_day', 5)
        if not isinstance(per_day, int) or isinstance(per_day, bool) or per_day < 1:
            per_day = 5
        return due_tick // per_day + 1

    def _due_message(self, due_tick, due_ticks):
        per_day = self.config.get('ticks_per_day', 5)
        if not isinstance(per_day, int) or isinstance(per_day, bool) or per_day < 1:
            per_day = 5
        days = due_ticks / per_day
        text = f'{days:g}' if days != int(days) else str(int(days))
        return f'预产期已记录：{due_ticks} 个时刻后（约 {text} 天，第 {self._due_day(due_tick)} 天，due_tick={due_tick}）。'

    def _present(self, node_id, place_id):
        """人物与地点之间必须在 presence_channel 上双向相连，不只看 profile.place。"""
        presence = self.config.get('presence_channel')
        if not isinstance(presence, str) or not presence:
            return False
        nodes = self.backend.network.nodes
        person = nodes.get(node_id)
        place = nodes.get(place_id)
        if person is None or place is None:
            return False

        def linked(source, target):
            return any(
                edge.target_node_id == target and presence in edge.metadata.channels
                for edge in source.interfaces
            )

        return linked(person, place_id) and linked(place, node_id)

    def _place_name(self, place):
        node = self.backend.network.nodes.get(place) if isinstance(place, str) else None
        return node.name if node is not None else str(place)

    def _reject(self, reason, message):
        return {'ok': False, 'reason': reason, 'charged': 0, 'message': message}

    def _insufficient(self, cost, spent):
        return {
            'ok': False,
            'reason': 'insufficient',
            'charged': 0,
            'cost': cost,
            'remaining': spent.get('remaining'),
            'message': spent.get('message') or f'行动值不足：需要 {cost} 点，本次未扣除。',
        }
