"""同一信号层内的有界异步后续访问；不继承调用者的锁或节点占用。"""
import asyncio
from contextvars import Context,ContextVar
import time

current_work=ContextVar('signal_layer_work',default=None)

class LayerWork:
    def __init__(self,signal,deadline,record):
        self.signal_id=signal.signal_id;self.limit=signal.max_deliveries;self.deadline=deadline
        self.record=record;self.tasks=[];self.count=0;self.closed=False
    def post(self,factory,label):
        if self.closed:raise RuntimeError('Signal layer has already finished')
        if self.count>=self.limit:raise RuntimeError('Signal deferred access budget exceeded')
        self.count+=1;entry=dict(target=label,status='queued');self.record.setdefault('deferred',[]).append(entry)
        async def run():
            token=current_work.set(self)
            try:
                entry['status']='processing'
                left=self.deadline-time.monotonic()
                if left<=0:raise TimeoutError('Signal deadline exceeded')
                result=await asyncio.wait_for(factory(),left)
                if isinstance(result,dict) and result.get('status')=='error':raise RuntimeError(str(result.get('error')))
                entry['status']='processed';return result
            except BaseException as error:
                entry.update(status='cancelled' if isinstance(error,asyncio.CancelledError) else 'failed',error=str(error) or type(error).__name__);raise
            finally:current_work.reset(token)
        task=asyncio.create_task(run(),context=Context());self.tasks.append(task)
        return dict(queued=True,signal_id=self.signal_id)
    async def drain(self):
        index=0
        while index<len(self.tasks):
            batch=self.tasks[index:];index=len(self.tasks)
            results=await asyncio.gather(*batch,return_exceptions=True)
            for result in results:
                if isinstance(result,BaseException):raise result
        self.closed=True
    async def cancel(self):
        self.closed=True
        for task in self.tasks:
            if not task.done():task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
