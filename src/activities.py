"""Full-resolution sampled activity flags; unknown readings remain explicit."""
import copy


class ActivityTimeline:
    MAX_SAMPLES=100000

    def __init__(self):
        self.samples=[]
        self.truncated_from_s=None

    def observe(self,t,values,segment=0):
        point=dict(t=t,segment=segment,values={k:v if isinstance(v,bool) else None for k,v in values.items()} if isinstance(values,dict) else None)
        if self.samples and self.samples[-1]['t']==t:self.samples[-1]=point
        elif len(self.samples)<self.MAX_SAMPLES:self.samples.append(point)
        elif self.truncated_from_s is None:self.truncated_from_s=t

    def summary(self):
        return dict(samples=copy.deepcopy(self.samples),truncated_from_s=self.truncated_from_s)
