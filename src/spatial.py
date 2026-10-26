"""Full-resolution position/counter samples for spatial gain maps."""
import copy
import math

FIELDS=('damage','gold_damage','kills','damage_taken_estimate','healing_received_estimate')


class SpatialTimeline:
    MAX_SAMPLES=100000

    def __init__(self):
        self.samples=[]
        self.truncated_from_s=None

    def observe(self,t,values,segment=0,position_segment=0):
        values=values or {}
        point=dict(t=t,segment=segment,position_segment=position_segment)
        xyz=values.get('xyz')
        point['xyz']=list(xyz) if isinstance(xyz,(tuple,list)) and len(xyz)==3 and all(isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) for v in xyz) else None
        for key in FIELDS:
            v=values.get(key)
            point[key]=v if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) else None
        if self.samples and self.samples[-1]['t']==t:self.samples[-1]=point
        elif len(self.samples)<self.MAX_SAMPLES:self.samples.append(point)
        elif self.truncated_from_s is None:self.truncated_from_s=t

    def summary(self):
        return dict(samples=copy.deepcopy(self.samples),truncated_from_s=self.truncated_from_s)
