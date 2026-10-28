// JSON document copies own their containers; immutable text bodies can be shared.
export function copyJson(value){
 if(value===null||typeof value!=='object')return value;
 return Array.isArray(value)?value.map(copyJson):Object.fromEntries(Object.entries(value).map(([key,item])=>[key,copyJson(item)]));
}
