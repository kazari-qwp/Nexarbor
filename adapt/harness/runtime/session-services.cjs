// Mount the installed DSH services that own session pressure and compaction.
module.exports=async function({host,native}){
 for(const name of ['dsh-token-meter','dsh-compaction-tool-result-pruner','dsh-compaction-image-offload','dsh-compaction-basic']){
  const service=native(name);await host.plugin(service.default??service);
 }
 if(!host.get('tokenMeter')||!host.get('compaction'))throw Error('Native DSH session compaction is not mounted');
};
