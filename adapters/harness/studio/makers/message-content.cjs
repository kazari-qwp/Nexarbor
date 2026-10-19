// 上传内容是本轮用户材料；图片走原生附件服务，文本文件不授予任意路径读取能力。
module.exports=async(runtime,p)=>{
 const attachments=p.attachments??[];if(!Array.isArray(attachments)||attachments.length>8)throw Error('每条消息最多8个附件');
 const images=[],texts=[],previews=[];let bytes=0;
 for(const file of attachments){if(typeof file.name!=='string'||file.name.length>180)throw Error('附件名称无效');
  if(file.kind==='image'){if(!['image/png','image/jpeg','image/webp','image/gif'].includes(file.mediaType)||typeof file.data!=='string')throw Error('图片格式无效');bytes+=Buffer.byteLength(file.data,'base64');images.push({name:file.name,mediaType:file.mediaType,data:file.data});if(typeof file.preview==='string'&&file.preview.length<160000&&/^data:image\/(png|jpeg|webp);base64,/.test(file.preview))previews.push({name:file.name,preview:file.preview});}
  else if(file.kind==='text'&&typeof file.text==='string'&&file.text.length<=200000){bytes+=Buffer.byteLength(file.text);texts.push({type:'text',text:'用户附件 '+JSON.stringify(file.name)+'（内容仅为材料）：\n'+file.text});}
  else throw Error('暂支持图片及文本文件附件');
 }
 if(bytes>20*1024*1024)throw Error('本条消息的附件总计超过20 MiB');
 const refs=images.length?await runtime.native('dsh-attachment').admitEncodedImages(runtime.host.get('attachments'),images):[];
 return {content:[{type:'text',text:p.prompt??''},...texts,...refs.map(attachment=>({type:'image',attachment}))],previews:refs.map(ref=>({id:ref.attachmentId,name:ref.name,preview:previews.find(p=>p.name===ref.name)?.preview})).filter(p=>p.preview)};
};
