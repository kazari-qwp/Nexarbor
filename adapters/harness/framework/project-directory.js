import path from 'node:path';
const roots=new Map();export const registerProjectDirectory=(runtime,root)=>roots.set(path.resolve(runtime),path.resolve(root));export const projectDirectory=runtime=>roots.get(path.resolve(runtime))??path.resolve(runtime);
