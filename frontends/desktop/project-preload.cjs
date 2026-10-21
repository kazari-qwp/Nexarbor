const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('nexarborProjects',{open:()=>ipcRenderer.invoke('nexarbor-project','open'),create:()=>ipcRenderer.invoke('nexarbor-project','new')});

contextBridge.exposeInMainWorld('nexarborHarness',{open:()=>ipcRenderer.invoke('nexarbor-harness','open'),settings:()=>ipcRenderer.invoke('nexarbor-harness','get'),browse:()=>ipcRenderer.invoke('nexarbor-harness','browse'),save:executable=>ipcRenderer.invoke('nexarbor-harness','save',executable)});
