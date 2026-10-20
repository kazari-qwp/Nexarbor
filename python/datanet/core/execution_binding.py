"""Executor-neutral graph configuration validation."""
def validate_execution_binding(node,network,definitions,*,allow_missing=False):
    """Validate the common execution binding without importing any host or studio."""
    binding=node.execution_binding
    if not binding:return
    if not isinstance(binding.get('executor'),str) or not binding['executor']:raise ValueError('执行器标识不能为空')
    if node.signal_type!='agent':raise ValueError('只有 Agent 节点可以绑定执行器')
    if set(binding)-{'executor','strength','channels','max_steps','timeout_seconds','prepare','channel_mode','channel_modes','tool_sources','model'}:raise ValueError('执行配置含未知字段')
    model=binding.get('model')
    if model is not None:
        if not isinstance(model,dict) or set(model)-{'connection','model','reasoning_effort','max_tokens','context_window'}:raise ValueError('模型配置只保存连接引用、模型和生成参数')
        for key in ('connection','model'):
            if not isinstance(model.get(key),str) or not model[key].strip() or len(model[key])>300:raise ValueError('模型连接和名称不能为空')
        if model.get('reasoning_effort') is not None and model['reasoning_effort'] not in ('off','minimal','low','medium','high','xhigh','max'):raise ValueError('模型思考强度无效')
        for key,limit in [('max_tokens',2000000),('context_window',4000000)]:
            if key in model and (type(model[key]) is not int or not 1<=model[key]<=limit):raise ValueError('模型生成参数无效：'+key)
    strength=binding.get('strength',0)
    if type(strength) not in (int,float) or not 0<=strength<=32:raise ValueError('执行器strength须为0至32')
    from .channel_filters import mode
    channels=binding.get('channels',[])
    mode(binding.get('channel_mode',binding.get('channel_modes',{}).get('channels','allow')))
    if not isinstance(channels,list) or any(not isinstance(c,str) or not c for c in channels) or len(set(channels))!=len(channels):raise ValueError('执行器channels须为唯一非空字符串列表')
    if type(binding.get('max_steps',12)) is not int or not 1<=binding.get('max_steps',12)<=100:raise ValueError('执行器max_steps须为1至100')
    timeout=binding.get('timeout_seconds',90)
    if type(timeout) not in (int,float) or not 1<=timeout<=600:raise ValueError('执行器timeout_seconds须为1至600')
    from .json_values import names
    names(binding.get('tool_sources',[]),'execution.tool_sources')
    prepare=binding.get('prepare',[])
    if not isinstance(prepare,list):raise ValueError('execution.prepare须为操作对象数组，不是true或单个对象')
    for item in prepare:
        if not isinstance(item,dict) or set(item)-{'node','module','operation','arguments','channels'} or not {'module','operation'}<=set(item):raise ValueError('prepare每项声明module/operation/arguments')
        target=network.nodes.get(item.get('node',node.node_id))
        if target is None:
            if allow_missing:continue
            raise ValueError('prepare引用不存在的节点')
        selected=item.get('channels',channels)
        if not isinstance(selected,list) or any(c not in channels for c in selected):raise ValueError('准备接口频道必须在执行器授权内')
        module=item['module'];operation=item['operation']
        if module not in target.modules:
            if allow_missing:continue
            raise ValueError('prepare引用未装配的模块：'+str(module))
        definition=definitions.get(module)
        if definition is None and allow_missing:continue
        if definition is None or operation not in definition.operations:raise ValueError('prepare引用未知模块操作')
        definition.validate(item.get('arguments',{}),definition.operations[operation]['parameters'])
