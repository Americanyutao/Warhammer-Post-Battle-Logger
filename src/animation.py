"""Bounded display interpolation; native counters and sorting remain exact."""
from dataclasses import dataclass


@dataclass
class Tween:
    source: object
    target: object
    started: float
    duration: float = 0.5

    def value(self, now):
        if self.source is None or self.target is None: return self.target
        t=max(0.0,min(1.0,(now-self.started)/self.duration))
        if t>=1: return self.target
        eased=t*t*(3-2*t)
        return self.source+(self.target-self.source)*eased

    def active(self, now):
        return self.source!=self.target and self.source is not None and self.target is not None and now<self.started+self.duration


class Transitions:
    def __init__(self):
        self.values={}
        self.generation=None

    def update(self, targets, now, generation=None):
        if generation!=self.generation:
            self.values.clear();self.generation=generation
        self.values={key:tween for key,tween in self.values.items() if key in targets}
        for key,target in targets.items():
            previous=self.values.get(key)
            if previous is None:
                self.values[key]=Tween(target,target,now)
            elif previous.target!=target:
                self.values[key]=Tween(previous.value(now),target,now)

    def snapshot(self, now):
        return {key:tween.value(now) for key,tween in self.values.items()}

    def active(self, now):
        return any(tween.active(now) for tween in self.values.values())
