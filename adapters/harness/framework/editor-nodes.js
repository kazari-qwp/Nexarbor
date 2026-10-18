const labels={node:'普通节点',agent:'Agent 节点',text_file:'文本节点',pulse:'脉冲节点'};
export function editorNode(kind,id,name){
 if(!Object.hasOwn(labels,kind))throw Error('未知节点类型');
 return {type:kind,node_id:id,name:name||labels[kind],description:'',management_parent_id:'root',divergence:-1,data_kind:null,parameters:kind==='agent'||kind==='text_file'?{file_path:'data/'+id+'.md'}:kind==='pulse'?{channels:['world.tick'],strength:4}:{},connections:{interfaces:[]},agent:null,modules:{},offered_tools:[],toolboxes:[],expose:[],execution:null,inputs:null,context_cursor:null};
}
export function editorNodes(){
 return Object.entries(labels).map(([id,name])=>{const node=editorNode(id,'template-'+id,name);return {id,name,description:{node:'通用节点，可装配模块与工具。',agent:'Agent 节点，可配置模型执行与上下文。',text_file:'文本节点，可编辑关联文档。',pulse:'脉冲节点，可配置频道与传播强度。'}[id],mode:'internal',snapshot:{nodes:[node],files:node.parameters.file_path?{[node.parameters.file_path]:''}:{},positions:{[node.node_id]:{x:0,y:0}}}};});
}
