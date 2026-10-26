"""Exact sampled presence, independent of decimated numeric graph history."""
import math


def nonnegative(value):
    return value if isinstance(value,(int,float)) and math.isfinite(value) and value>=0 else None


class EffectTimeline:
    MAX_SAMPLES = 100000

    def __init__(self):
        self.effects, self.indices, self.samples = [], {}, []
        self.segments=[]
        self.values=[]
        self.truncated_from_s = None

    def observe(self, t, effects, segment=0, damage_scale=None):
        if len(self.samples)>=self.MAX_SAMPLES and self.samples[-1][0]!=t:
            if self.truncated_from_s is None:self.truncated_from_s=t
            return
        indices = None
        values={}
        if isinstance(effects,list):
            indices = []
            occurrences={}
            for effect in effects:
                if not isinstance(effect,dict) or not isinstance(effect.get('key'),str):
                    indices = None
                    break
                key = effect['key']
                occurrence=occurrences.get(key,0)
                occurrences[key]=occurrence+1
                # Native list identity preserves simultaneous entries. Legacy or
                # mod samples without identity retain each duplicate in its own lane.
                identity=(key,effect.get('instance_id'),occurrence if not effect.get('instance_id') else 0)
                if identity not in self.indices:
                    self.indices[identity] = len(self.effects)
                    self.effects.append(dict(key=key,name=effect.get('name') or key,
                        polarity=effect.get('polarity','other')))
                index = self.indices[identity]
                if index not in indices:indices.append(index)
                values[str(index)]=dict(intensity=nonnegative(effect.get('intensity')),
                    damage_scale=nonnegative(damage_scale))
            if indices is not None:indices.sort()
            else:values={}
        point = [t,indices]
        if self.samples and self.samples[-1][0] == t:
            self.samples[-1] = point
            self.segments[-1]=segment
            self.values[-1]=values
        elif len(self.samples) < self.MAX_SAMPLES:
            self.samples.append(point)
            self.segments.append(segment)
            self.values.append(values)

    def summary(self):
        # Do not show an effect seen only in a superseded paused observation.
        used = {i for _,active in self.samples for i in (active or [])}
        order = sorted(used)
        remap = {old:new for new,old in enumerate(order)}
        return dict(effects=[dict(self.effects[i]) for i in order],
            samples=[[t,[remap[i] for i in active] if active is not None else None] for t,active in self.samples],
            segments=list(self.segments),
            values=[{str(remap[int(i)]):dict(value) for i,value in reading.items() if int(i) in remap} for reading in self.values],
            truncated_from_s=self.truncated_from_s)
