// Optional file-format fields; absence or null means no framework parameter UI.
export const repeatMetadata=value=>Object.fromEntries(['repeat_unit_count','repeat_unit'].filter(k=>value?.[k]!==undefined).map(k=>[k,structuredClone(value[k])]));
export function validRepeatMetadata(value){
 if(value?.repeat_unit_count==null)return true;
 const ids=value.repeat_unit,known=new Set((value.nodes??[]).map(n=>n.node_id));
 return Number.isInteger(value.repeat_unit_count)&&value.repeat_unit_count>=1&&value.repeat_unit_count<=100&&Array.isArray(ids)&&ids.length>0&&ids.every(id=>typeof id==='string'&&known.has(id))&&new Set(ids).size===ids.length;
}
