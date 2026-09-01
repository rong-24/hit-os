import sys
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# ---------- constants ----------
HZ = 100

P_NULL    = 0
P_NEW     = 1
P_READY   = 2
P_RUNNING = 4
P_WAITING = 8
P_EXIT    = 16

STATE_MAP = {
    "N": P_NEW,
    "J": P_READY,
    "R": P_RUNNING,
    "W": P_WAITING,
    "E": P_EXIT,
}

GRAPH_TITLE = r"""
-----===< COOL GRAPHIC OF SCHEDULER >===-----

             [Symbol]   [Meaning]
         ~~~~~~~~~~~~~~~~~~~~~~~~~~~
             number     PID or tick
              "-"       New or Exit 
              "#"       Running
              "|"       Ready
              ":"       Waiting
                    / Running with 
              "+" -|     Ready 
                    \and/or Waiting

-----===< !!!!!!!!!!!!!!!!!!!!!!!!! >===-----
"""

USAGE = """
Usage:
  {0} /path/to/process.log [PID1] [PID2] ... [-x PID1 [PID2] ... ] [-m] [-g]

Example:
  # Include process 6, 7, 8 and 9 in statistics only. (Unit: tick)
  {0} /path/to/process.log 6 7 8 9

  # Exclude process 0 and 1 from statistics. (Unit: tick)
  {0} /path/to/process.log -x 0 1

  # Include process 6 and 7 only and print graphic. (Unit: millisecond)
  {0} /path/to/process.log 6 7 -m -g

  # Include all processes and print graphic. (Unit: tick)
  {0} /path/to/process.log -g
"""

# ---------- models ----------
@dataclass
class Process:
    pid: int
    # events: list of (time, state_bitmask_at_time)
    # We store events as time->bitmask to merge multiple states in same tick.
    events: Dict[int, int] = field(default_factory=dict)

    def add_state(self, t: int, s: int) -> None:
        cur = self.events.get(t, 0)
        self.events[t] = cur | s

    def begin_time(self) -> int:
        return min(self.events.keys())

    def end_time(self) -> int:
        return max(self.events.keys())

    def timeline(self) -> List[Tuple[int, int]]:
        # return sorted list of (time, state_mask)
        return sorted(self.events.items(), key=lambda x: x[0])

    def state_at(self, t: int) -> int:
        # Determine effective state at tick t:
        # - if exact event exists: return that (possibly combined mask)
        # - else return the latest prior tick's state (single or combined)
        items = self.timeline()
        last_state = P_NULL
        for tt, ss in items:
            if tt < t:
                # If multiple flags at same tick, keep as-is as last_state
                last_state = ss
                continue
            if tt == t:
                return ss
            break
        return last_state

    def turnaround_time(self) -> int:
        return self.end_time() - self.begin_time()

    def _accumulate(self, target: int) -> int:
        # Accumulate durations where the (effective) state equals target only.
        # For combined masks, we count the segment if target bit is present.
        t0 = self.begin_time()
        t1 = self.end_time()
        total = 0
        prev = self.state_at(t0)
        seg_start = t0

        for t in range(t0 + 1, t1 + 1):
            cur = self.state_at(t)
            if cur != prev:
                if (prev & target) != 0:
                    total += (t - seg_start)
                seg_start = t
                prev = cur

        # tail segment
        if (prev & target) != 0:
            total += (t1 + 1 - seg_start)  # inclusive end -> +1

        return total

    def waiting_time(self) -> int:
        return self._accumulate(P_READY)

    def cpu_time(self) -> int:
        return self._accumulate(P_RUNNING)

    def io_time(self) -> int:
        return self._accumulate(P_WAITING)


class ProcessPool:
    def __init__(self) -> None:
        self.procs: Dict[int, Process] = {}

    def get(self, pid: int) -> Optional[Process]:
        return self.procs.get(pid)

    def ensure(self, pid: int) -> Process:
        if pid not in self.procs:
            self.procs[pid] = Process(pid=pid)
        return self.procs[pid]

    def pids(self) -> List[int]:
        return sorted(self.procs.keys())

    def items(self):
        return self.procs.items()

    def filtered_pids(self, include: List[int], exclude: List[int]) -> List[int]:
        pids = self.pids()
        if include:
            pids = [p for p in pids if p in include]
        if exclude:
            pids = [p for p in pids if p not in exclude]
        return pids


# ---------- parsing ----------
def parse_args(argv: List[str]) -> Tuple[str, List[int], List[int], bool, bool]:
    if len(argv) < 2:
        print(USAGE.format(argv[0]))
        sys.exit(0)

    path = argv[1]
    include: List[int] = []
    exclude: List[int] = []
    unit_ms = False
    graphic = False

    ex_mark = False
    for arg in argv[2:]:
        if arg == "-m":
            unit_ms = True
            continue
        if arg == "-g":
            graphic = True
            continue
        if arg == "-x":
            ex_mark = True
            continue

        try:
            pid = int(arg)
        except ValueError:
            print(f"Bad argument '{arg}'")
            sys.exit(-1)

        if not ex_mark:
            include.append(pid)
        else:
            exclude.append(pid)

    return path, include, exclude, unit_ms, graphic


def load_log(path: str) -> ProcessPool:
    pool = ProcessPool()

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            prev_line = None
            prev_time = -1

            for lineno, line in enumerate(f, start=1):
                raw = line.strip("\n")
                if not raw.strip():
                    continue

                # skip exact duplicate line
                if prev_line is not None and raw == prev_line:
                    continue
                prev_line = raw

                parts = raw.split("\t")
                if len(parts) != 3:
                    # tolerate malformed line
                    continue

                try:
                    pid = int(parts[0].strip())
                    st = parts[1].strip().upper()
                    t = int(parts[2].strip())
                except ValueError:
                    continue

                if st not in STATE_MAP:
                    # unknown state -> ignore rather than crash
                    continue

                # tolerate slight disorder
                if t < prev_time:
                    # keep going; do not update prev_time
                    pass
                else:
                    prev_time = t

                p = pool.ensure(pid)
                p.add_state(t, STATE_MAP[st])

    except OSError:
        print(f"Error: Could not read file {path}")
        sys.exit(0)

    # Patch: process 0 is frequently missing/buggy in some environments.
    # If pid 0 doesn't exist, create a minimal placeholder anchored at earliest time.
    if pool.get(0) is None:
        # choose a conservative anchor; if log empty, use 0
        all_times = []
        for _, proc in pool.items():
            all_times.extend(list(proc.events.keys()))
        anchor = min(all_times) if all_times else 0
        p0 = pool.ensure(0)
        p0.add_state(anchor, P_NEW)
        p0.add_state(anchor, P_RUNNING)

    return pool


# ---------- statistics ----------
def begin_end(pool: ProcessPool, pids: List[int]) -> Tuple[int, int]:
    begin = None
    end = None
    for pid in pids:
        p = pool.get(pid)
        if p is None or not p.events:
            continue
        b = p.begin_time()
        e = p.end_time()
        begin = b if begin is None else min(begin, b)
        end = e if end is None else max(end, e)
    return (begin or 0, end or 0)


def throughput(pool: ProcessPool, pids: List[int]) -> float:
    b, e = begin_end(pool, pids)
    dur = float(e - b)
    if dur <= 0:
        return 0.0
    return len(pids) * HZ / dur


def print_table(pool: ProcessPool, pids: List[int], unit_ms: bool) -> None:
    if unit_ms:
        unit = "ms"
        scale_num = 1000
        scale_den = HZ
    else:
        unit = "tick"
        scale_num = 1
        scale_den = 1

    def conv(x: int) -> int:
        return int(x * scale_num / scale_den)

    print(f"(Unit: {unit})")
    print("Process    Turnaround    Waiting    CPU Burst    I/O Burst")

    t_sum = 0.0
    w_sum = 0.0
    cnt = 0

    for pid in pids:
        p = pool.get(pid)
        if p is None or not p.events:
            continue
        tt = p.turnaround_time()
        wt = p.waiting_time()
        cpu = p.cpu_time()
        io = p.io_time()

        print(f"{pid:7d}    {conv(tt):10d}    {conv(wt):7d}    {conv(cpu):9d}    {conv(io):9d}")

        t_sum += (tt * scale_num / scale_den)
        w_sum += (wt * scale_num / scale_den)
        cnt += 1

    att = (t_sum / cnt) if cnt else 0.0
    awt = (w_sum / cnt) if cnt else 0.0
    print(f"Average:  {att:10.2f}    {awt:7.2f}")
    print(f"Throughout: {throughput(pool, pids):.2f}/s")


def print_graphic(pool: ProcessPool, pids: List[int]) -> None:
    b, e = begin_end(pool, pids)
    print(GRAPH_TITLE)

    # Track previous state for "PID label" printing
    prev_state: Dict[int, int] = {pid: P_NULL for pid in pids}

    for t in range(b, e + 1):
        line = f"{t:5d} "
        for pid in pids:
            p = pool.get(pid)
            cur = p.state_at(t) if p is not None else P_NULL

            # choose symbol
            if cur & P_NEW:
                ch = "-"
            elif cur & P_EXIT:
                ch = "-"
            elif (cur & P_RUNNING) and (cur & (P_READY | P_WAITING)):
                ch = "+"
            elif cur & P_RUNNING:
                ch = "#"
            elif cur & P_READY:
                ch = "|"
            elif cur & P_WAITING:
                ch = ":"
            else:
                ch = " "

            line += ch

            # label on transition (excluding blanks)
            if cur != prev_state[pid] and cur != P_NULL:
                line += f"{pid:<3d}"
            else:
                line += "   "
            prev_state[pid] = cur

        print(line)


def main() -> None:
    path, include, exclude, unit_ms, graphic = parse_args(sys.argv)
    pool = load_log(path)
    pids = pool.filtered_pids(include, exclude)

    print_table(pool, pids, unit_ms)
    if graphic:
        print_graphic(pool, pids)


if __name__ == "__main__":
    main()
