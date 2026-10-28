"""停用损坏模块并保留配置；修复源码后由正常工厂重新装配。"""
from copy import deepcopy
from domain.core import Module, CallableTool

class UnavailableModule(Module):
    def __init__(self, key, record, reason):
        super().__init__(key, **{k:record[k] for k in ('channels','strength','channel_mode') if k in record})
        self.unavailable_reason = str(reason)
        self.config = deepcopy(record.get('config', {}))
        self.state = deepcopy(record.get('state', {}))
        self.saved_dependencies = list(record.get('modules', []))
        def visit(item):
            if 'tool' in item:
                self.tools._add(CallableTool(item['tool'], self.refuse, item.get('description',''), deepcopy(item.get('parameters',{}))))
            for member in item.get('members',[]):visit(member)
        visit(record.get('tools', {}))

    def refuse(self, **parameters):
        raise RuntimeError('模块不可用：'+self.module_id+'；'+self.unavailable_reason)
