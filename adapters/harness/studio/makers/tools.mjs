const object=properties=>({type:'object',properties,additionalProperties:false}),str={type:'string'};
const tool=(name,description,properties={},required=[])=>({name,description,parameters:{...object(properties),required}});
export function makerTools(kind,allowCreation=false){
 const common=[tool('list_files','列出当前工作副本及可按需阅读的教程。'),tool('read_file','读取副本内文件，使用相对路径。',{path:str,start_line:{type:'integer',minimum:1},line_count:{type:'integer',minimum:1,maximum:400}},['path']),tool('write_file','创建或覆盖当前副本文件；规范和参考只读。',{path:str,content:str},['path','content']),tool('edit_file','精确替换一处文本；不唯一时先重新读取。',{path:str,old:str,new:str},['path','old','new']),tool('catalog_modules','按职责检索已发布模块的接口、默认配置和携带工具，先复用。',{query:str}),tool('validate','运行宿主验证及已收集的测试，读取失败原因。')];
 if(kind==='network')common.push(tool('node_template','取得合法的核心节点骨架，填好模块和连接后写入 network.json。',{kind:{enum:['node','agent','text_file','pulse']},id:str,name:str},['kind','id','name']));
 if(kind==='network'&&allowCreation)common.push(tool('request_component','委托统一模块／工具 Agent 制作缺少的通用组件。返回任务编号，稍后查状态。',{kind:{enum:['module','tool']},name:str,requirement:str},['kind','name','requirement']),tool('component_status','检查当前网络制作任务委托的组件；通过验证并发布后才可引用。',{task:str},['task']));
 return common;
}
