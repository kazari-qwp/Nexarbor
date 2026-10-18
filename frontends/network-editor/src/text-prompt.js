import './text-prompt.css';
// Electron 不支持 window.prompt；复用浏览器原生 dialog 的模态与键盘行为。
export function textPrompt(message,initial=''){
 return new Promise(resolve=>{
  const dialog=document.createElement('dialog');dialog.className='client-text-prompt';dialog.setAttribute('aria-label',message);
  const form=document.createElement('form');form.method='dialog';const label=document.createElement('label');label.textContent=message;
  const input=document.createElement('input');input.value=initial;input.name='text';label.append(input);form.append(label);
  const actions=document.createElement('div');actions.className='modal-actions';
  for(const [value,text] of [['cancel','取消'],['confirm','确定']]){const button=document.createElement('button');button.value=value;button.textContent=text;if(value==='confirm')button.className='primary';actions.append(button);}
  form.append(actions);dialog.append(form);document.body.append(dialog);
  dialog.addEventListener('close',()=>{const value=dialog.returnValue==='confirm'?input.value:null;dialog.remove();resolve(value);},{once:true});
  dialog.showModal();input.focus();input.select();
 });
}
