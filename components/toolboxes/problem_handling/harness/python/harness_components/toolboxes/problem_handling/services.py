from uuid import uuid4

def check_feedback_owner(self, p):
    binding = self.agents.get(p['target'], {})
    allowed = binding.get('manager_id') == p['actor'] and any((r['actor'] == p['target'] for r in self.feedback))
    return {'allowed': allowed}

def report_feedback(self, p):
    actor = p['actor']
    if actor not in self.agents:
        raise ValueError('Reporter has no Agent binding')
    if p['category'] not in {'missing_tool', 'permission_denied', 'other'}:
        raise ValueError('Unknown feedback category')
    message = {'missing_tool': '工具缺失', 'permission_denied': '权限不足'}.get(p['category'])
    if message is None:
        message = p.get('message')
        if not isinstance(message, str) or not message.strip() or len(message.strip()) > 80:
            raise ValueError('Custom feedback must contain 1 to 80 characters')
        message = message.strip()
    report = {'id': uuid4().hex, 'actor': actor, 'creator_node_id': self.agents[actor].get('creator_node_id'), 'manager_id': self.agents[actor].get('manager_id'), 'category': p['category'], 'message': message, 'status': 'blocked'}
    self.feedback.append(report)
    self.agents[actor]['activity'] = 'blocked'
    self.agents[actor]['last_feedback_id'] = report['id']
    return report

def register(services):
    services.rpc('check_feedback_owner', check_feedback_owner, mutation=False)
    services.rpc('report_feedback', report_feedback, mutation=True)
register_routes = register

def register(services):
    register_routes(services)
    services.initializers.append(lambda backend: setattr(backend, 'feedback', []))
    services.snapshotters.append(lambda backend: {'feedback': backend.feedback})
    services.restorers.append(lambda backend, document: setattr(backend, 'feedback', document.get('feedback', [])))
    services.statusters.append(lambda backend: {'feedback': backend.feedback})
