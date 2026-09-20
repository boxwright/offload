# What you need to run this, stated plainly

This tool makes a Claude subscription last longer by doing most of the typing on a model that runs
on your own machine. That only works if your machine can run a capable model. Most laptops cannot.
Run `install/preflight.sh` first: it reads your machine and tells you, and it installs nothing.

## The short version

| You need | Why |
|---|---|
| A Linux box with an NVIDIA GPU with **24 GB of VRAM or more** (32 GB is what we tested) | the local model lives in GPU memory |
| **32 GB of system RAM or more**, 60 GB of free disk | the model file is 20 GB; the sandbox image is 2.4 GB |
| Docker with the NVIDIA Container Toolkit | the model server and the sandbox run in containers |
| Your own **Claude Pro or Max** subscription | planning, review and rescue still use Claude; this tool never shares accounts |
| Comfort pasting one command into a terminal | the installer does the rest |

If you do not have the GPU, this tool is not for you yet. Smaller models are planned; none is shipped or tested.

## Tested configurations

Only rows marked **measured** have numbers we produced ourselves. Everything else is labeled for what it is.

| Machine | Model and settings | Status | Numbers |
|---|---|---|---|
| Ryzen 9800X3D, **RTX 5090 32 GB**, 60 GB RAM, Ubuntu 26.04, llama.cpp server in Docker | Qwen3.8-27B, Q5_K_XL (20.2 GB file), 196k context, flash attention, quantized KV cache, 1 slot, MTP speculative decoding | **measured** 2026-09-16/17 | prefill 2,896 tok/s; decode 129 tok/s; follow-up turn on a cached 33k-token prefix 0.55 s; VRAM 29.9 of 32 GB; container RAM steady at about 31 GiB |
| The same box, **the default install**: upstream `ghcr.io/ggml-org/llama.cpp:server-cuda`, `install/compose.yaml` as shipped, 131k context | Qwen3.8-27B Q5_K_XL | **measured** 2026-09-20 in a maintenance window | decode 67.3 tok/s with speculative decoding off; **85 tok/s (prose) to 92 tok/s (code)** with it on, draft acceptance 44-84 %; GPU memory 23.9 GB off, 25.4 GB on (**+1.5 GB**, as the installer estimates); a cold model reload took 6 s from a warm disk cache; a three-turn tool task through sandbox → proxy → model took 9.7 s |
| NVIDIA 24 GB cards (RTX 3090, 4090) | Qwen3.8-27B at 4-bit, shorter context | **untested by us** | expected to fit; context and speed unknown until someone measures |
| MacBook Pro **M5, 32 GB** unified memory, MLX | GLM-4.7-Flash 4-bit (16 GB, mixture-of-experts), 202k context | **measured** 2026-09-11/16, as a fast side tier, **not** as this tool's worker | decode 38 tok/s; prefill 274-495 tok/s, about a tenth of the 5090. An agent harness sends a prefix of 20k+ tokens per session, so a cold start costs about a minute before the first token. A dense 27B model is slower still. **Verdict: a 32 GB laptop is not a practical host for the coding worker.** |
| Apple Silicon with 64 GB or more (Max, Ultra) | a 27B-class model at 4-8 bit | **untested by us** | prefill speed is the number to measure first |
| Anything with less than 22 GB of VRAM | none | **not supported** | a smaller-model option is planned |

How the measured numbers were produced: `calibration/` holds the five test-scored coding tasks and both
runners; `docs/evidence/` holds the benchmark JSON. Rerun them on your box and open an issue with your row.

## Speculative decoding (an install option)

The model ships its own multi-token-prediction head. With it on, the server drafts a few tokens per step and
verifies them. Output is bit-identical; only speed changes. Measured on the RTX 5090 (2026-09-11, 196k context):

| Text | Off | On | Speed-up | Draft acceptance |
|---|---|---|---|---|
| repetitive code | 67 tok/s | 169 tok/s | 2.5x | 97% |
| novel code | 67 tok/s | 126 tok/s | 1.9x | 64% |
| technical prose | 67 tok/s | 125 tok/s | 1.9x | 63% |
| novel prose | 67 tok/s | 104 tok/s | 1.6x | 47% |

Cost: about **1.5 GB more GPU memory** (27.6 to 29.2 GB on that box). No second model file. **System RAM does not
matter for this**; on our box it ran fine with 30 GB of RAM before the upgrade to 60. The installer estimates your
headroom and labels the option *recommended* (1 GB or more left; the estimate predicts 29.6 GB where we measured 29.2 GB) or *not recommended*. The memory estimate is
scaled from one measured machine; the speed-up is measured. It works with the standard llama.cpp server image
(`--spec-type draft-mtp`): on the default install we measured 67 tok/s off and 85-92 tok/s on. The custom build on
our box is faster still (104-169 tok/s); the table above is that build.

## What it saves, measured on real jobs

| Job | Local model | Claude | Claude's share |
|---|---|---|---|
| Fix a planted bug in a small repo (3-4 steps) | 60-130 s, 3-5 sessions | plan + review, 17-25 s | 2 calls, about 20 cents at list prices |
| Add a function with a new test file | 84 s, 4 sessions | 36 s, 3 calls | 26 cents |
| Write a 33-test suite for this engine, 446 lines, 5 files | 740 s, 7 sessions | 36 s, 2 calls | 53 cents |

"Cents at list prices" is a yardstick, not a bill: the calls draw from your subscription's usage limits.
The same jobs done entirely by Claude re-read 130k-190k cached tokens **per small task** (measured in `calibration/RESULTS.md`).

## What it cannot do

- It does not make a small GPU run a big model.
- The local model is strong on well-specified coding steps (5/5 on our calibration set, 33/33 tests on a real job). It is unmeasured on vague specs and large unfamiliar codebases. When it stalls, the engine escalates to Claude and records that it did.
- It does not run on Windows or as a Mac-hosted daemon today, and a 32 GB laptop is too slow at prefill to be the worker (measured above).
