"""Share current exit observations across isolated paper roles in one tick."""
from datetime import UTC,datetime


class SharedExitObservations:
    def __init__(self,loader,*,max_age_seconds,clock=None):
        if max_age_seconds<=0:raise ValueError('positive observation lifetime required')
        self.loader=loader;self.max_age_seconds=max_age_seconds
        self.clock=clock or (lambda:datetime.now(UTC));self.cache={}

    def __call__(self,pair):
        now=self.clock();cached=self.cache.get(pair)
        if cached:
            observed,value,error=cached
            age=(now-observed).total_seconds()
            if 0<=age<=self.max_age_seconds:
                if error is not None:raise error
                return value[0],list(value[1])
        # Anchor before acquisition: a slow request must not gain a fresh lifetime.
        try:
            decision,reasons=self.loader(pair)
            value=(decision,tuple(reasons));error=None
        except Exception as exc:
            value=None;error=exc
        self.cache[pair]=(now,value,error)
        if error is not None:raise error
        if (self.clock()-now).total_seconds()>self.max_age_seconds:
            self.cache.pop(pair,None)
            raise TimeoutError('exit observation exceeded its lifetime')
        return value[0],list(value[1])
