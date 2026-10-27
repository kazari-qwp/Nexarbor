import fs from 'node:fs/promises';
import {editNetwork} from '../adapt/harness/studio/makers/edit-network.mjs';
const input=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const before=JSON.stringify(input.document);
if(input.expect_failure){try{editNetwork(input.document,input.commands,input.library);throw Error('expected rejection')}catch(error){if(error.message==='expected rejection')throw error;if(JSON.stringify(input.document)!==before)throw Error('failed batch mutated original');await fs.writeFile(process.argv[3],JSON.stringify({rejected:true,message:error.message}));}}
else await fs.writeFile(process.argv[3],JSON.stringify(editNetwork(input.document,input.commands,input.library)));
