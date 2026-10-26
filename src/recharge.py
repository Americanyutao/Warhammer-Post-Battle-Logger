"""Recharge extrema and time-weighted means from observed battle-time samples."""
import math


def valid_rate(army):
    value=army.get('recharge_per_second')
    return value if army.get('maximum')!=0 and isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0 else None


class RechargeStats:
    def __init__(self):
        self.pending=None
        self.highest=self.lowest=None
        self.total=self.count=self.weighted=self.covered=0

    def observe(self,t,army,segment):
        point=dict(t=t,rate=valid_rate(army),segment=segment)
        previous=self.pending
        if previous and previous['t']==t:
            self.pending=point
            return
        if previous:
            rate=previous['rate']
            if rate is not None:
                self.highest=rate if self.highest is None else max(self.highest,rate)
                self.lowest=rate if self.lowest is None else min(self.lowest,rate)
                self.total+=rate;self.count+=1
            if rate is not None and point['rate'] is not None and segment==previous['segment'] and t>previous['t']:
                duration=t-previous['t'];self.weighted+=rate*duration;self.covered+=duration
        self.pending=point

    def summary(self):
        rate=self.pending['rate'] if self.pending else None
        values=[v for v in (self.highest,rate) if v is not None]
        lowest=[v for v in (self.lowest,rate) if v is not None]
        count=self.count+(rate is not None)
        total=self.total+(rate if rate is not None else 0)
        average=self.weighted/self.covered if self.covered>0 else total/count if count else None
        return dict(highest=max(values) if values else None,lowest=min(lowest) if lowest else None,
                    average=average,covered_seconds=self.covered,observed_samples=count,
                    average_method='battle_time_weighted' if self.covered>0 else 'sample_mean' if count else 'unavailable')
