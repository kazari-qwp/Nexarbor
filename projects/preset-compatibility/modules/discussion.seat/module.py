"""讨论席位：发布真实 Agent 在讨论组中的角色与显示名称。"""

from datanet.core.module_protocol import ComponentResult

ROLES = ('leader', 'recorder', 'member')


def _seat(ctx):
    """读取并规范化席位配置；显示名称为空时回退到节点名称。"""
    role = ctx.config.get('role', 'member')
    if role not in ROLES:
        raise ValueError('席位角色必须是 leader、recorder 或 member。')

    name = ctx.config.get('name', '')
    if not isinstance(name, str):
        raise ValueError('显示名称必须是字符串。')
    name = name.strip()
    if not name:
        name = str(ctx.metadata().get('name') or '').strip() or ctx.node_id
    return role, name


async def execute(ctx, activation):
    if activation.kind != 'access':
        return ComponentResult(status='error', error='讨论席位只接受访问调用。')
    if activation.operation != 'describe':
        return ComponentResult(
            status='error',
            error='不支持的讨论席位操作：{}'.format(activation.operation),
        )

    try:
        role, name = _seat(ctx)
        ctx.publish_metadata({'role': role, 'name': name})
    except Exception as error:
        return ComponentResult(status='error', error=str(error))

    return ComponentResult(data={'id': ctx.node_id, 'name': name, 'role': role})
