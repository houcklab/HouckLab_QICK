from datetime import datetime
import json
import math
from pathlib import Path
import sys
import time


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


QUBIT = "q3"
T1_POINTS = 71
T1_SHOTS = 1000
RECORD_WORDS = 2
RECORD_BASE = 32


def estimate_stream_overhead(
    *,
    dmem_words,
    record_base,
    record_words,
    records,
    measured_words,
    measured_seconds,
):
    values = tuple(int(value) for value in (
        dmem_words,
        record_words,
        records,
        measured_words,
    ))
    dmem_words, record_words, records, measured_words = values
    record_base = int(record_base)
    measured_seconds = float(measured_seconds)
    if min(dmem_words, record_words, records, measured_words) <= 0:
        raise ValueError("stream dimensions must be positive")
    if record_base < 0 or record_base >= dmem_words:
        raise ValueError("record base must be inside data memory")
    if not math.isfinite(measured_seconds) or measured_seconds < 0:
        raise ValueError("measured time must be finite and non-negative")
    bank_records = (dmem_words - record_base) // (2 * record_words)
    if bank_records <= 0:
        raise ValueError("stream bank capacity must be positive")
    bank_words = bank_records * record_words
    bank_count = math.ceil(records / bank_records)
    seconds_per_word = measured_seconds / measured_words
    return {
        "bank_records": int(bank_records),
        "bank_words": int(bank_words),
        "bank_count": int(bank_count),
        "single_read_us_per_word": float(seconds_per_word * 1e6),
        "estimated_single_read_stream_s": float(
            bank_count * bank_words * seconds_per_word
        ),
    }


def _callable_reader(owner):
    try:
        reader = getattr(owner, "read_dmem", None)
    except Exception:
        return None
    return reader if callable(reader) else None


def _time_bulk_reader(reader, address, words):
    started = time.perf_counter()
    result = reader(int(address), int(words))
    elapsed = time.perf_counter() - started
    return elapsed, len(result)


def _time_single_reader(reader, address, words):
    started = time.perf_counter()
    for offset in range(int(words)):
        reader(int(address) + offset)
    return time.perf_counter() - started


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
        outerFolder,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import (
        makeProxy,
    )

    now = datetime.now()
    output = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_T1_runtime_diagnostic"
    )
    output.mkdir(parents=True, exist_ok=False)
    connected_at = time.perf_counter()
    soc, soccfg = makeProxy()
    connection_s = time.perf_counter() - connected_at
    dmem_words = int(soccfg["tprocs"][0]["dmem_size"])
    records = int(T1_POINTS * T1_SHOTS)
    bank_records = (dmem_words - RECORD_BASE) // (2 * RECORD_WORDS)
    measured_words = int(bank_records * RECORD_WORDS)
    bulk = {}
    for name, owner in (("tproc", soc.tproc), ("soc", soc)):
        reader = _callable_reader(owner)
        if reader is None:
            bulk[name] = {"available": False}
            continue
        try:
            elapsed, returned = _time_bulk_reader(
                reader, RECORD_BASE, measured_words
            )
            bulk[name] = {
                "available": True,
                "elapsed_s": float(elapsed),
                "returned_words": int(returned),
            }
        except Exception as exc:
            bulk[name] = {
                "available": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
    single_reader = getattr(soc.tproc, "single_read")
    single_elapsed = _time_single_reader(
        single_reader, RECORD_BASE, measured_words
    )
    estimate = estimate_stream_overhead(
        dmem_words=dmem_words,
        record_base=RECORD_BASE,
        record_words=RECORD_WORDS,
        records=records,
        measured_words=measured_words,
        measured_seconds=single_elapsed,
    )
    usable_bulk = any(
        item.get("available") and "error" not in item
        for item in bulk.values()
    )
    diagnosis = (
        "bulk_dmem_available"
        if usable_bulk
        else "per_word_pyro_dmem_bottleneck"
    )
    result = {
        "platform": "QICK",
        "qubit": QUBIT,
        "diagnosis": diagnosis,
        "controller_connection_s": float(connection_s),
        "dmem_words": int(dmem_words),
        "bulk_readers": bulk,
        "single_read_benchmark_words": int(measured_words),
        "single_read_benchmark_s": float(single_elapsed),
        "representative_t1_points": int(T1_POINTS),
        "representative_t1_shots": int(T1_SHOTS),
        "representative_t1_records": int(records),
        **estimate,
    }
    (output / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"output={output}")


if __name__ == "__main__":
    main()
