// 通用工具图片输出：先纳入原生附件库，再用 ContentBlock 呈现，避免把 base64 当文字发给模型。
const fs=require('node:fs/promises');
const FORMAT='nexarbor-tool-content/v1';
exports.prepare=async(runtime,value)=>{
 if(value?.format!==FORMAT)return value;
 if(!Array.isArray(value.content)||value.content.length>16)throw Error('工具内容块无效');
 const images=[];let size=0;
 for(const block of value.content){
  if(block.type==='text'){if(typeof block.text!=='string')throw Error('工具文本无效');continue;}
  if(block.type!=='image'||!['image/png','image/jpeg','image/webp','image/gif'].includes(block.mediaType)||typeof block.data!=='string'||!block.data.length||!/^[A-Za-z0-9+/]*={0,2}$/.test(block.data))throw Error('工具图片格式无效');
  size+=Buffer.byteLength(block.data,'base64');if(size>8*1024*1024||images.length>=4)throw Error('工具图片超过大小或数量限制');
  images.push({name:typeof block.name==='string'?block.name.slice(0,160):'工具图片',mediaType:block.mediaType,data:block.data});
 }
 const refs=images.length?await runtime.native('dsh-attachment').admitEncodedImages(runtime.host.get('attachments'),images):[];
 let index=0;return {format:FORMAT,content:value.content.map(block=>block.type==='image'?{type:'image',attachment:refs[index++]}:{type:'text',text:block.text})};
};
exports.render=(_args,value)=>value?.format===FORMAT?value.content:[{type:'text',text:JSON.stringify(value)}];
exports.previews=async(runtime,messages)=>{
 const result={},refs=new Map();for(const message of messages)for(const block of message.content??[])if(block.type==='image'&&block.attachment?.attachmentId)refs.set(block.attachment.attachmentId,block.attachment);
 for(const [id,ref]of [...refs].slice(-24)){try{const data=await fs.readFile(runtime.host.get('attachments').imageHostPath(ref));if(data.length<=8*1024*1024)result[id]='data:'+ref.mediaType+';base64,'+data.toString('base64');}catch(error){if(error.code!=='ENOENT')throw error;}}
 return result;
};
