# Offline hardware planner

The **Hardware planner** page is available to signed-in users. It estimates memory for a hypothetical GPU deployment; it does not install models, change the running model, or enable concurrent inference. The current application processes one generation at a time with a bounded waiting queue.

## Inputs and output

Choose connected concurrent users, the percentage actually generating at once, model, weight format, total context budget, and memory per GPU. Advanced inputs include desired per-answer token rate, answer length, headroom, retrieval working RAM, and an optional measured aggregate token rate per GPU. All calculations and the frozen model catalog work without internet.

The result shows memory-driven GPU count, optional throughput-driven count, planned count (the greater of these), host RAM allowance, and physical CPU core allowance. GiB means 1024³ bytes. Model profile selection is a simulation. Only the bundled Bonsai model is installed; the Qwen profiles need separate provisioning and runtime compatibility testing.

## Memory model

- Active sequences = ceil(users × activity percentage / 100).
- Model weights use actual GGUF file sizes, including format overhead.
- FP16 KV cache per sequence = 2 × attention layers × KV heads × head dimension × context tokens × 2 bytes.
- Context includes instructions, retrieved evidence, history, and generated answer, not just the user's question.
- Bonsai's hybrid architecture uses 16 full attention layers out of 64. A further **0.20 GiB per sequence** for recurrent state is a planning assumption, not a measured allocation.
- Runtime reserve per GPU = max(1.5 GiB, 10% of model weights).
- GPU footprint = (weights + runtime reserve + sequence count × sequence state) × (1 + headroom percentage / 100).
- Each GPU holds a complete replica. Memory slots/card are rounded down, and required cards are rounded up. If even one sequence cannot fit, the planner reports failure and the minimum larger memory class for one sequence. It never sums small cards into a fictitious large card.

This version does not model tensor parallelism, CPU offload, compressed KV caches, unified memory, prefix sharing, model-specific workspaces, or multi-server placement. Actual allocations depend on the inference backend. Headroom is an allowance, not a proof against out-of-memory errors.

## Speed, RAM, and CPU

Required aggregate output rate = active sequences × desired tokens/sec per answer. Answer tokens / desired rate is a **target decode duration**, excluding queueing, retrieval, and prompt prefill; it is not a latency prediction.

Without a benchmark, GPU count only covers memory. An optional sustained aggregate decode rate per GPU gives ceil(required rate / measured rate) GPUs as a provisional throughput estimate. Use measurements for the exact model, quantization, GPU, context, and representative batching/concurrency. Changing model, GPU class, context, or quantization in the UI clears the measurement. Comparisons never reuse a benchmark: all comparison rows use memory alone. A benchmark still does not guarantee time to first token or a service-level objective.

RAM and CPU are explicitly **engineering heuristics for GPU-resident inference**, not vendor requirements or benchmark results:

```
RAM baseline GiB = 8 + weights_GiB × 1.25 + retrieval_working_GiB
                   + 2 × planned_GPU_count + 0.04 × active_sequences
RAM allowance = baseline × 1.25, rounded up to a listed memory class
CPU cores baseline = max(8, 4 + 4 × planned_GPU_count + ceil(active_sequences / 8))
CPU cores allowance = rounded up to a listed physical-core class
```

Use a modern AVX2-capable host CPU as an initial compatibility assumption. These figures do not prescribe a specific CPU SKU, motherboard, PCIe topology, network, power supply, or chassis. Large card counts may require several hosts and a separate deployment design. Document ingestion and large indexes can need much more host memory. VRAM alone cannot predict speed; bandwidth, GPU generation, backend, prefill, batching, and interconnect matter.

## Catalog provenance

Catalog snapshot: **2026-10-16**, stored in `config/capacity-models.json`, with source URLs and exact weight byte counts. Local Bonsai architecture and file size were read from the bundled GGUF. Qwen architecture comes from official model configurations; GGUF file sizes come from the corresponding official Qwen repositories:

- [Qwen3-4B configuration](https://huggingface.co/Qwen/Qwen3-4B/resolve/main/config.json) and [GGUF files](https://huggingface.co/Qwen/Qwen3-4B-GGUF/tree/main).
- [Qwen3-8B configuration](https://huggingface.co/Qwen/Qwen3-8B/resolve/main/config.json) and [GGUF files](https://huggingface.co/Qwen/Qwen3-8B-GGUF/tree/main).
- [Qwen3-14B configuration](https://huggingface.co/Qwen/Qwen3-14B/resolve/main/config.json) and [GGUF files](https://huggingface.co/Qwen/Qwen3-14B-GGUF/tree/main).
- [Qwen3-32B configuration](https://huggingface.co/Qwen/Qwen3-32B/resolve/main/config.json) and [GGUF files](https://huggingface.co/Qwen/Qwen3-32B-GGUF/tree/main).
- [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/tree/master/tools/server) for serving and parallel decoding concepts. The calculator's assumptions are not a claim that the bundled deployment already enables these features.

Before procurement, benchmark the chosen model on candidate hardware using real document lengths and expected concurrency. Record throughput, time to first token, tail latency, peak GPU/host memory, and ingestion load.
