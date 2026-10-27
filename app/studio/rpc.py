"""制作服务的宿主路由；沿用原读写分类和长操作时限。"""
from inspect import isawaitable

METHODS={
    'append_requirement':False,'catalog':False,'prepare_agent':False,'create':False,
    'read':False,'dependencies':False,'maker_tool':False,'maker_scope':False,
    'environment':False,'observe':False,'copy_current':False,'release_read':False,
    'revision':False,'project_modules':False,'save':False,'delete_file':False,
    'delete_workspace':False,'frontend':False,'frontend_preview':False,
    'validate':False,'job':False,'cancel':False,'publish':True,'mount':True,
    'unmount':True,'pulse':True,'reconcile':True,'state':False,'draft':False,
    'apply':True,'graph_validate':False,'runtime_settings':False,
}

def register(transport):
    from .skill_resources import parse_skill
    transport.routes['skill_parse']=parse_skill
    def route(name,mutation,p):
        def invoke():
            value=getattr(transport.backend.studio,name)(p)
            return transport.runtime.run(value,timeout=86460) if isawaitable(value) else value
        if name=='apply':
            # 沿用原 StudioTransport：图应用的返回版本必须是外围事务提交后的编号。
            with transport.backend._transaction_lock:
                result=transport.backend.perform('studio_apply',invoke)
                result['commit']=transport.backend.store.head
                return result
        return transport.backend.perform('studio_'+name,invoke) if mutation else invoke()
    for name,mutation in METHODS.items():
        transport.routes['studio_'+name]=lambda p,name=name,mutation=mutation:route(name,mutation,p)
