"""Bounded full-reader fixture workload; never attaches to the game."""
import json
from pathlib import Path
import statistics
import sys
import time

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT/'src'), str(PROJECT/'tests')]
from aggregate import Battle
from fixtures import BattleFixture
from logfile import LogWriter, load_key
from resources import atomic_json, process_resources


def main():
    fixture = BattleFixture(40, 40)
    memory = fixture.memory
    battle = Battle(keep_history=False, max_gap=80)
    path = PROJECT/'build'/f'reader-benchmark-{time.time_ns()}.wh3log'
    key = load_key(PROJECT/'build/demo.key', create=True)
    writer = LogWriter(path, key, dict(source='sparse-memory-fixture', maximum_interval_s=80))
    costs, calls, sizes = [], [], []
    wall, cpu = time.perf_counter(), time.process_time()
    for tick in range(60):
        memory.u(fixture.script+0x4a4, tick*1000)
        before_calls, before_bytes = memory.calls, memory.bytes_read
        started = time.perf_counter()
        frame = fixture.reader.normalized(fixture.sample())
        battle.observe(frame)
        writer.write(frame)
        battle.summary()  # Worker publication cost, without a redraw.
        costs.append((time.perf_counter()-started)*1000)
        calls.append(memory.calls-before_calls)
        sizes.append(memory.bytes_read-before_bytes)
    writer.close(dict(reason='fixture_completed'))
    result = dict(source='80-unit sparse-memory fixture, not live game performance',
        includes=['native roster/fields/visibility adapter', 'aggregation', 'encrypted writing', 'live summary creation'],
        excludes=['Windows process reads', 'Tk redraw', 'game frame times'],
        samples=len(costs), units=80, ms_average=statistics.mean(costs),
        ms_p95=statistics.quantiles(costs,n=20)[18], read_calls_average=statistics.mean(calls),
        read_bytes_average=statistics.mean(sizes), cpu_seconds=time.process_time()-cpu,
        wall_seconds=time.perf_counter()-wall, encrypted_bytes=path.stat().st_size, **process_resources())
    atomic_json(PROJECT/'build/reader-benchmark.json',result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
