import {randomBytes} from 'node:crypto';
export function uuidv7() {
  const b=randomBytes(16);b.writeUIntBE(Date.now(),0,6);b[6]=(b[6]&15)|0x70;b[8]=(b[8]&63)|0x80;
  const h=b.toString('hex');return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}
export function redactText(value) {
  let text=String(value?.message??value??'');
  for(const [key,secret] of Object.entries(process.env))if(/key|token|password|secret/i.test(key)&&secret.length>=8)text=text.split(secret).join('[redacted]');
  return text.replace(/Bearer\s+[^\s"']+/gi,'Bearer [redacted]');
}
