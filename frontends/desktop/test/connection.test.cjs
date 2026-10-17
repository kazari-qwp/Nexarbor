const test=require('node:test'),assert=require('node:assert/strict');
const {validateAddress,localNavigation}=require('../connection.cjs');
const token='a'.repeat(64);
test('connection requires a credentialed local root; restored local branches remain navigable',()=>{
 assert.equal(validateAddress('http://127.0.0.1:1234/#token='+token),'http://127.0.0.1:1234/#token='+token);
 for(const url of ['https://example.com/#token='+token,'file:///etc/passwd','http://user@127.0.0.1:1234/#token='+token,'http://127.0.0.1:1234/api#token='+token,'http://127.0.0.1:1234/?token='+token,'http://127.0.0.1:1234/#token=short'])assert.throws(()=>validateAddress(url));
 assert.equal(localNavigation('http://127.0.0.1:5678/'),true);assert.equal(localNavigation('https://example.com/'),false);assert.equal(localNavigation('http://127.0.0.1:1234/api'),false);
});
