# Model and Hardware Evaluation Matrix

**Status:** Active  
**Issue:** #81  
**Milestone:** M1.5 Translation Quality Upgrade

---

## Purpose

This document defines the evidence-based framework for deciding when and whether to
scale local hardware, and which model tiers to test before making that decision.
Hardware upgrades are expensive and irreversible; model benchmarks are cheap and
repeatable.  The decision to expand hardware must be justified by benchmark
results, not by assumptions about model size.

---

## Why hardware alone will not fix translation quality

Adding VRAM or compute unlocks larger models, but larger models do not
automatically produce better subtitles.  Translation quality depends on:

1. **Prompt design** — a well-crafted prompt to a 14B model often outperforms a
   poorly prompted 70B model.
2. **Translation workflow** — using direct LLM translation (rather than
   MarianMT → LLM polish) removes a lossy intermediate step.
3. **QC signal** — without a QC pass the pipeline cannot detect or suppress
   hallucinations, register errors, and over-literal phrases regardless of
   model size.
4. **Reference data** — without a fixed benchmark corpus there is no reliable
   signal that a bigger model is producing better output.

**The required sequence before any hardware expansion:**

1. Establish a translation benchmark corpus with fixed Japanese source and
   human-reviewed English reference subtitles.
2. Measure baseline quality (WER / BLEU / chrF) with the current workstation
   and the models already installed.
3. Add direct LLM translation (issue #75) and per-segment QC.
4. Re-benchmark.  Only if quality is still limited by model capacity — not by
   prompt, workflow, or QC — does a hardware upgrade become justified.

---

## Runtime profiles

Three local runtime profiles are defined below.  Each profile maps to a
hardware tier and determines which model sizes are viable.

### Profile 1 — Current workstation (`rtx_4090_24gb`)

| Property | Value |
|---|---|
| GPU | NVIDIA RTX 4090 (24 GB GDDR6X) |
| RAM | 64 GB DDR5 |
| CPU | AMD Ryzen 9 7900X or equivalent |
| Storage | NVMe SSD, ≥ 2 TB |
| `runtime.profile` in `config.yaml` | `prod` |

**Maximum viable model sizes (Ollama GGUF Q4):**

| Stage | Max model | Fits after ASR unloads? |
|---|---|---|
| ASR | Whisper large-v3 (~4 GB) | n/a |
| LLM translation / polish | 32B Q4 (~19 GB) | Yes — 20 GB headroom after ASR |
| Simultaneous ASR + LLM | 7B Q4 | Only with quantized ASR |

**Config profile name:** `prod`  
**Benchmark metadata `hardware_profile` key:** `rtx_4090_24gb`

---

### Profile 2 — Larger single-machine local AI (`ai_workstation_96gb`)

A dedicated AI workstation with 96+ GB of VRAM (e.g., two RTX 4090s in
NVLink, or a single NVIDIA RTX 6000 Ada 48 GB × 2, or equivalent).

| Property | Value |
|---|---|
| GPU VRAM | 96 GB (e.g., 2 × 48 GB or 4 × 24 GB) |
| RAM | 128 GB DDR5 |
| `runtime.profile` in `config.yaml` | `ai_workstation` (to be added) |

**Maximum viable model sizes:**

| Stage | Max model |
|---|---|
| LLM translation / polish | 70B Q4 (~42 GB), 72B Q5 (~49 GB) |
| Simultaneous ASR + LLM | 70B Q4 |
| Experimental | 405B+ with multi-GPU loading |

**When this profile becomes justified:**  
Benchmark evidence that the 32B model on the current workstation is hitting a
quality ceiling (see [Quality bottleneck](#quality-bottleneck-definition)) and
that a 70B test run on borrowed hardware or via direct GGUF swap shows a
≥ 2-point chrF improvement on the benchmark corpus.

**Config profile name:** `ai_workstation`  
**Benchmark metadata `hardware_profile` key:** `ai_workstation_96gb`

---

### Profile 3 — Multi-machine local processing (`multi_node`)

A small cluster of 2–4 machines where model inference is split across nodes
(e.g., llama.cpp with `--rpc` or vLLM tensor-parallel).

| Property | Value |
|---|---|
| Nodes | 2–4 machines, each with ≥ 24 GB VRAM |
| Coordination | llama.cpp RPC or vLLM tensor-parallel |
| `runtime.profile` in `config.yaml` | `multi_node` (to be added) |

**Maximum viable model sizes:**  
Effectively unlimited within the total combined VRAM across all nodes.  A
two-node setup with 2 × RTX 4090 (48 GB combined) can run 70B Q4; four nodes
can run 405B-class models.

**When this profile becomes justified:**  
- The 70B+ model tier demonstrably improves quality beyond the 32B tier
  (benchmark evidence required, see below).
- **AND** throughput on a single machine is a confirmed bottleneck
  (see [Throughput bottleneck](#throughput-bottleneck-definition)).
- **AND** the volume of content warrants multi-machine investment.

**Config profile name:** `multi_node`  
**Benchmark metadata `hardware_profile` key:** `multi_node`

---

## Model tiers

The following model tiers define the test ladder.  Move to the next tier only
when the current tier has been benchmarked and a quality ceiling confirmed.

| Tier | Example models | Typical VRAM (Q4) | Profile required |
|---|---|---|---|
| Small / dev | qwen2.5:7b, llama3.1:8b | 5–6 GB | `dev` (RTX A3000 6 GB) |
| 14B | qwen2.5:14b-instruct | 9 GB | `dev` or `prod` |
| 32B | qwen2.5:32b | 19 GB | `prod` (RTX 4090) |
| 70B-class | qwen2.5:72b, llama3.3:70b | 42–48 GB | `ai_workstation` |
| 405B+ | llama3.1:405b (full) | 240+ GB | `multi_node` |

**Test order:**  Start with the 14B tier on the current hardware.  If 14B shows
a quality ceiling (defined below), test 32B.  Only after 32B also shows a
ceiling should Profile 2 hardware be considered.

---

## How to record benchmark results

Run the pipeline in benchmark mode against the fixed translation benchmark
corpus (see `fixtures/benchmark_translation/`):

```bash
python main.py <fixture_video_or_stub> --mode benchmark --profile prod
```

The output `benchmark_results.json` records per-candidate metrics.  To attach
hardware and model metadata, add a `benchmark_run` block to the JSON artifact
(or record separately in a log):

```json
{
  "benchmark_run": {
    "hardware_profile": "rtx_4090_24gb",
    "model": "qwen2.5:32b",
    "quantization": "q4_k_m",
    "context_window": 6,
    "runtime_seconds": 123.4,
    "quality_summary": "BLEU 52.1 / chrF 71.3 / WER 0.29 vs reference"
  },
  "video": "...",
  "reference_id": "...",
  "candidates": [...],
  "comparisons": [...]
}
```

All fields map to the optional metadata schema described in the
[Benchmark metadata fields](#benchmark-metadata-fields) section.

Store each run's JSON under a versioned filename so runs can be compared over
time:

```
benchmark_results_<date>_<model_slug>_<hw_profile>.json
```

Example: `benchmark_results_2026-05-01_qwen32b_rtx4090.json`

---

## Quality bottleneck definition

A **quality bottleneck** is confirmed when all of the following conditions hold:

1. The benchmark corpus scores for the current model tier are:
   - BLEU < 45  **OR**  chrF < 65  **OR**  WER > 0.35
   - These thresholds represent a quality level that is clearly below
     acceptable subtitle quality for the project's use cases.
2. Increasing the context window (up to the model's maximum) does not improve
   the scores by ≥ 2 chrF points.
3. Prompt refinement (testing at least 3 prompt variants) does not improve the
   scores by ≥ 2 chrF points.
4. A test run with the next model tier (e.g., 32B instead of 14B) on any
   available hardware — including borrowed hardware or a temporary cloud
   instance used for evaluation only — shows a ≥ 2-point chrF improvement on
   the same benchmark corpus.

A **quality improvement** is counted when:
- chrF improves by ≥ 2 points corpus-level, **AND**
- BLEU improves by ≥ 1 point corpus-level, **AND**
- WER does not increase.

A single-point improvement in one metric is not sufficient evidence; all three
conditions must hold simultaneously.

---

## Throughput bottleneck definition

A **throughput bottleneck** is confirmed when all of the following conditions hold:

1. Quality benchmarks confirm that a larger model (requiring more hardware)
   produces acceptable translation quality on the benchmark corpus.
2. Processing a typical episode-length asset (22–24 minutes, ~600 subtitle
   cues) takes more than **4 hours** end-to-end on the current hardware at the
   required model size.
3. The bottleneck is confirmed as inference time — not disk I/O, audio
   extraction, or post-processing — by profiling the pipeline with
   `--log-level DEBUG`.

If quality is acceptable on the current hardware but throughput is the
concern, the preferred mitigation order is:

1. Reduce quantization level (e.g., Q4 → Q5) if quality is marginal.
2. Use batched translation where the model and context window permit.
3. Only then consider Profile 2 hardware.

Multi-machine processing (Profile 3) is justified only when **both** a quality
ceiling at 32B **and** a throughput bottleneck at 70B on single-machine
Profile 2 hardware have been confirmed by benchmark evidence.

---

## Benchmark metadata fields

The following fields should be recorded for every benchmark run that is used
to inform a hardware or model decision.  They may be embedded in
`benchmark_results.json` under a top-level `benchmark_run` key, or recorded
in a separate sidecar file.

| Field | Type | Required | Description |
|---|---|---|---|
| `hardware_profile` | string | yes | One of `rtx_4090_24gb`, `ai_workstation_96gb`, `multi_node`, or a custom slug |
| `model` | string | yes | Fully qualified model name, e.g. `qwen2.5:32b` |
| `quantization` | string | yes | Quantization level, e.g. `q4_k_m`, `q5_k_m`, `f16` |
| `context_window` | integer | yes | Number of surrounding source segments provided as context |
| `runtime_seconds` | float | yes | Wall-clock time for the full benchmark run |
| `quality_summary` | string | yes | One-line summary: e.g. `BLEU 52.1 / chrF 71.3 / WER 0.29` |
| `translation_engine` | string | no | One of `marian`, `llm_direct`, `hybrid` |
| `prompt_mode` | string | no | One of `literal`, `natural_subtitle`, `accuracy_first` |
| `notes` | string | no | Free-form notes (prompt changes, hardware anomalies, etc.) |

---

## Decision matrix

Use the following matrix to determine which action to take based on benchmark
evidence.

| Current quality | Current throughput | Recommended action |
|---|---|---|
| chrF ≥ 65, WER ≤ 0.30 | < 4 h / episode | No hardware change needed; refine prompts or QC |
| chrF < 65 or WER > 0.35 | Any | Fix quality first: improve prompts, add QC, try larger context window before any hardware change |
| chrF < 65 after prompt/QC improvement | Any | Test 32B on current hardware; if still below threshold, evaluate Profile 2 |
| chrF ≥ 65 with 32B on current hardware | > 4 h / episode | Evaluate Profile 2 for throughput, or accept slower runs |
| chrF ≥ 65 only with 70B | > 4 h / episode on Profile 2 | Evaluate Profile 3 multi-machine |
| chrF ≥ 65 on current hardware | ≤ 4 h / episode | Current hardware is sufficient; no upgrade justified |

---

## Related documents

- `docs/EVALUATION.md` — benchmark metrics and candidate selection.
- `docs/BENCHMARK_QUICKSTART.md` — running benchmark mode.
- `docs/architecture/adr-001-local-first-platform.md` — local-first constraints.
- `fixtures/benchmark_translation/` — benchmark corpus fixtures.
- `acceptance/81-model-hardware-evaluation.md` — acceptance criteria for this document.
