const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('networkView',{
 receive:callback=>{ipcRenderer.on('network-view:render',(_event,scene)=>callback(scene));ipcRenderer.send('network-view:boot');},
 ready:value=>ipcRenderer.send('network-view:ready',value)
});
