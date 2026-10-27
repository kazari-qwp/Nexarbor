import fs from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';

// Windows scanners or concurrent readers may briefly hold the destination open.
export async function replaceFile(temporary,destination){
 for(let attempt=0;;attempt++)try{await fs.rename(temporary,destination);return;}
 catch(error){if(!['EPERM','EACCES','EBUSY'].includes(error.code)||attempt>=8){await fs.unlink(temporary).catch(()=>{});throw error;}await delay(Math.min(15*2**attempt,200));}
}
