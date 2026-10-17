"""Offline capacity planning: transparent memory math, not a speed guarantee."""
import json
import math
from pathlib import Path

GIB = 1024 ** 3
GPU_CLASSES = [8, 12, 16, 24, 32, 48, 80, 96, 141, 192]
RAM_CLASSES = [16, 32, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 4096]


def number(data, name, default, low, high, integer=False):
    value = data.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"Invalid {name}.")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {name}.") from exc
    if not math.isfinite(result) or not low <= result <= high or (integer and result != int(result)):
        raise ValueError(f"{name} must be between {low} and {high}.")
    return int(result) if integer else result


def round_class(value, classes):
    return next((item for item in classes if item >= value), math.ceil(value / 256) * 256)


class CapacityPlanner:
    def __init__(self, config):
        self.config = config
        self.catalog = json.loads((config.root / "config/capacity-models.json").read_text(encoding="utf-8"))
        self.profiles = {profile["id"]: profile for profile in self.catalog["profiles"]}

    def models(self):
        result = []
        for profile in self.profiles.values():
            row = dict(profile)
            model_path = Path(self.config.settings["model_file"])
            row["bundled"] = profile["id"] == "bonsai-27b" and model_path.is_file() and model_path.stat().st_size == profile["weights_bytes"].get("PTQ1_0")
            result.append(row)
        return {"version": self.catalog["version"], "verified_date": self.catalog["verified_date"],
                "models": result, "gpu_classes_gib": GPU_CLASSES,
                "current_deployment": {"generation_slots": 1, "queue_size": self.config.settings["queue_size"]}}

    def estimate(self, data, compare=True):
        if not isinstance(data, dict):
            raise ValueError("Expected a planning request.")
        model_id = data.get("model_id", "bonsai-27b")
        if not isinstance(model_id, str) or model_id not in self.profiles:
            raise ValueError("Choose a model from the offline catalog.")
        profile = self.profiles[model_id]
        quant = data.get("quantization", next(iter(profile["weights_bytes"])))
        if not isinstance(quant, str) or quant not in profile["weights_bytes"]:
            raise ValueError("That quantization is not available for the selected model.")
        users = number(data, "users", 10, 1, 10000, True)
        activity = number(data, "activity_percent", 100, 1, 100)
        active = math.ceil(users * activity / 100)
        context = number(data, "context_tokens", 8192, 512, profile["max_context"], True)
        output = number(data, "answer_tokens", 500, 32, 4000, True)
        if output >= context:
            raise ValueError("Answer length must be smaller than the total context budget.")
        target = number(data, "target_tps", 12, 1, 200)
        gpu = number(data, "gpu_gib", 24, 4, 256, True)
        safety = number(data, "headroom_percent", 25, 10, 100)
        index_ram = number(data, "knowledge_ram_gib", 2, .5, 256)
        benchmark = data.get("benchmark_tps")
        if isinstance(benchmark, bool):
            raise ValueError("Invalid benchmark_tps.")
        measured = None if benchmark in (None, "", 0, "0") else number(data, "benchmark_tps", None, .1, 100000)
        weight = profile["weights_bytes"][quant] / GIB
        layers = profile.get("attention_layers", profile["layers"])
        # Separate K and V in full-attention layers, FP16 throughout. Hybrid
        # recurrent-state reserve is explicitly a heuristic in the catalog.
        kv = 2 * layers * profile["kv_heads"] * profile["head_dim"] * context * 2 / GIB
        recurrent = profile.get("recurrent_gib_per_sequence", 0)
        per_sequence = kv + recurrent
        runtime = max(1.5, weight * .10)
        factor = 1 + safety / 100
        base = weight + runtime
        single = (base + per_sequence) * factor
        minimum_class = next((item for item in GPU_CLASSES if item >= single), None)
        slots = math.floor((gpu / factor - base) / per_sequence) if gpu / factor > base else 0
        slots = max(0, slots)
        # One complete model replica per GPU. This avoids pretending that sums
        # of small GPU memories form a single large GPU without tensor parallelism.
        memory_count = math.ceil(active / slots) if slots else None
        throughput_count = math.ceil(active * target / measured) if measured else None
        planned_count = max(memory_count, throughput_count or 1) if memory_count else None
        busiest = math.ceil(active / planned_count) if planned_count else 1
        allocated_kv = per_sequence * busiest
        needed_per_gpu = (base + allocated_kv) * factor
        # Host RAM and CPU are planning heuristics for GPU-resident inference,
        # same-host replicas and the selected in-memory knowledge working set.
        ram_base = 8 + weight * 1.25 + index_ram + (planned_count or 1) * 2 + active * .04
        ram = round_class(ram_base * 1.25, RAM_CLASSES)
        cores_raw = max(8, 4 + 4 * (planned_count or 1) + math.ceil(active / 8))
        cores = round_class(cores_raw, [8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256])
        result = {
            "model_id": model_id, "model_name": profile["name"], "quantization": quant,
            "inputs": {"users": users, "activity_percent": activity, "context_tokens": context,
                       "answer_tokens": output, "target_tps": target, "gpu_gib": gpu,
                       "headroom_percent": safety, "knowledge_ram_gib": index_ram, "benchmark_tps": measured},
            "active_generations": active, "weights_gib": round(weight, 3),
            "kv_gib_per_sequence": round(kv, 4), "recurrent_gib_per_sequence": recurrent,
            "runtime_reserve_gib_per_gpu": round(runtime, 3), "memory_slots_per_gpu": slots,
            "single_sequence_vram_gib": round(single, 2), "minimum_single_gpu_class_gib": minimum_class,
            "memory_gpu_count": memory_count, "throughput_gpu_count": throughput_count,
            "planned_gpu_count": planned_count, "gpu_class_gib": gpu,
            "total_provisioned_vram_gib": planned_count * gpu if planned_count else None,
            "estimated_used_vram_per_gpu_gib": round(needed_per_gpu, 2) if planned_count else None,
            "ram_gib": ram if planned_count else None, "ram_floor_gib": round(ram_base, 1) if planned_count else None,
            "cpu_physical_cores": cores if planned_count else None,
            "required_aggregate_tokens_per_second": round(active * target, 1),
            "target_decode_seconds": round(output / target, 1),
            "throughput_basis": "user_supplied_benchmark" if measured else "not_benchmarked",
            "speed_guaranteed": False, "current_generation_slots": 1,
            "current_queue_size": self.config.settings["queue_size"],
            "assumptions": {"kv_cache": "FP16", "placement": "one complete GPU-resident model replica per GPU",
                            "memory_unit": "GiB (1024^3 bytes)", "cpu_and_ram": "engineering heuristics, not benchmarks",
                            "recurrent_state": profile.get("note", "Not applicable to dense GQA profiles.")},
            "sources": profile["sources"], "catalog_date": self.catalog["verified_date"]}
        if compare:
            rows = []
            for candidate in self.profiles.values():
                choice = quant if quant in candidate["weights_bytes"] else next(iter(candidate["weights_bytes"]))
                estimate = self.estimate({**result["inputs"], "model_id": candidate["id"], "quantization": choice,
                                          "benchmark_tps": None}, False)
                rows.append({key: estimate[key] for key in ("model_id", "model_name", "quantization", "weights_gib",
                             "memory_gpu_count", "planned_gpu_count", "ram_gib", "cpu_physical_cores", "minimum_single_gpu_class_gib")})
            result["comparison"] = rows
        return result
