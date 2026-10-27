import {defineConfig} from 'vite';
export default defineConfig({base:'./',build:{outDir:'../../build/network-editor',emptyOutDir:true,rollupOptions:{input:{main:'index.html',networkView:'network-view.html'}}}});
