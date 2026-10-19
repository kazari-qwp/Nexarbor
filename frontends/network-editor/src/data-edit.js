// 只合并仍与请求前相同的数据节点；不会覆盖等待期间的其他草稿修改。
const normal=value=>value.replaceAll('\\','/');
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function mergeDataEdit(document,value){
 const {beforeNode,beforeFiles,node,files}=value,nodes=document.network?.nodes??document.nodes,current=nodes.find(n=>n.node_id===beforeNode.node_id);
 if(!same(current,beforeNode)||node.node_id!==beforeNode.node_id)throw Error('节点配置已经变化，请重新读取后保存数据');
 const roots=['file_path','content_path','metadata_path','db_path','directory','storage_path'].map(k=>beforeNode.parameters?.[k]).filter(p=>typeof p==='string').map(normal);
 const owned=source=>Object.fromEntries(Object.entries(source??{}).map(([key,data])=>[normal(key),data]).filter(([key])=>roots.some(root=>key===root||key.startsWith(root.replace(/\/$/,'')+'/'))).sort(([a],[b])=>a.localeCompare(b)));
 if(!same(owned(document.files),owned(beforeFiles)))throw Error('节点数据已经变化，请重新读取后保存');
 const next=structuredClone(document),target=next.network?.nodes??next.nodes;target[target.findIndex(n=>n.node_id===node.node_id)]=structuredClone(node);Object.assign(next.files,structuredClone(files));return next;
}

export const isDataNode=node=>!!node&&(['text_file','value','csv','sqlite','knowledge_collection','llamaindex'].includes(node.type)||!!node.modules?.['knowledge.collection']);
const dataBinding=node=>JSON.stringify([node.type,Object.fromEntries(['file_path','db_path','directory','storage_path','table_name','key_column'].filter(k=>node.parameters?.[k]!==undefined).map(k=>[k,typeof node.parameters[k]==='string'?normal(node.parameters[k]):node.parameters[k]]))]);
export function mergeClearedData(document,value){
 const {beforeNode,node,files,roots=[]}=value,next=structuredClone(document),nodes=next.network?.nodes??next.nodes,current=nodes.find(n=>n.node_id===beforeNode.node_id);
 if(!current||dataBinding(current)!==dataBinding(beforeNode))throw Error('真实数据已清空，但草稿的存储位置已改变，请刷新查看');
 if(current.type==='value')current.parameters.value=null;
 if(node.modules?.['knowledge.collection']&&current.modules?.['knowledge.collection'])current.modules['knowledge.collection'].state=structuredClone(node.modules['knowledge.collection'].state);
 for(const name of Object.keys(next.files))if(roots.some(([root,kind])=>normal(name)===normal(root)||kind==='directory'&&normal(name).startsWith(normal(root).replace(/\/$/,'')+'/')))delete next.files[name];
 Object.assign(next.files,structuredClone(files));return next;
}
