module.exports=function countRequest(entry,limit){
 if(entry.steps>=limit)throw Error('模型请求次数达到上限 '+limit);
 return ++entry.steps;
};
