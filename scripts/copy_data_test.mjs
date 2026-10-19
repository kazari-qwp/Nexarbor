import fs from 'node:fs/promises';
import {copySubnet,pasteSubnet} from '../frontends/network-editor/src/subnets.js';
const input=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const snapshot=copySubnet(input.document,input.ids,input.mode??'internal');
const result=pasteSubnet(input.document,{mode:input.mode??'internal',snapshot},{x:400,y:100},input.catalog??{});
await fs.writeFile(process.argv[3],JSON.stringify({snapshot,...result}));
