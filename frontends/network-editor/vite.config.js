import {defineConfig} from 'vite';
export default defineConfig({base:'./',build:{outDir:'../../extensions/editor/capabilities/network_editor/web',emptyOutDir:true,rollupOptions:{input:{main:'index.html',networkView:'network-view.html'}}}});
