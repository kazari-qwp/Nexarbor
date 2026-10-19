const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('nexarborProjects',{open:()=>ipcRenderer.invoke('nexarbor-project','open'),create:()=>ipcRenderer.invoke('nexarbor-project','new')});
