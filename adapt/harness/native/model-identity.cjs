const {createHash}=require('node:crypto');

module.exports=function providerIdentity(profile){
 const identity=profile.identity??{
  kind:profile.kind,
  connection:profile.id??profile.credentials??'',
  protocol:profile.protocol??'deepseek-account',
  endpoint:profile.base_url?.replace(/\/$/,'')??'https://api.deepseek.com',
 };
 return 'nexarbor-'+createHash('sha256').update(JSON.stringify(identity)).digest('hex').slice(0,32);
};
