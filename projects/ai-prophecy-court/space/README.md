---
title: AI Prophecy Court
emoji: 🍄
colorFrom: yellow
colorTo: green
sdk: gradio
app_file: app.py
python_version: "3.11"
pinned: false
license: mit
short_description: Put public AI predictions on trial in a two-model roast battle.
tags:
  - gradio
  - custom-ui
  - build-small-hackathon
  - thousand-token-wood
models:
  - nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16
  - openbmb/MiniCPM4.1-8B
  - openbmb/VoxCPM2
datasets:
  - build-small-hackathon/ai-prophecy-court-presence
---

# AI Prophecy Court

AI leaders made the predictions. Two small models write the closing arguments.
You are the jury.

AI Prophecy Court turns preserved public posts into playful, source-linked
court cases. Pick a roast division, give two models the same evidence packet,
vote for the sharper argument, and reveal which model wrote each roast.

## Why AI Is Load-Bearing

The central experience is a blind creative comparison between
`NVIDIA-Nemotron-3-Nano-4B-BF16` and `MiniCPM4.1-8B`. The models do the fun
thing: they interpret the rhetoric of a real claim and independently produce
the competing punchlines. A reviewed curated battle keeps the app usable
during cold starts or provider outages.

## Product Guardrails

- Every quoted statement links to its preserved source.
- The court roasts public claims, not identity, appearance, family, or private
  life.
- Verdicts evaluate rhetoric inside the collected dataset; they are not
  external fact checks.
- Model identities stay hidden until the visitor votes.
- No model used by the project exceeds 32B parameters.

## Stack

- Gradio `Server` for the Space backend and typed callable API
- React, TypeScript, Vite, and shadcn-style primitives for the custom frontend
- `json-render` for schema-driven courtroom scenes
- Modal gateway for optional live model calls and aggregate vote storage
- Hugging Face dataset provenance with deterministic docket candidate building

The Space remains functional without external secrets. Live roast generation
activates when `MODAL_RUNTIME_URL` and `MODAL_RUNTIME_TOKEN` are configured.

## Links

- [Source repository](https://github.com/Ashish-Soni08/ai-prophecy-court)
- [Presence dataset](https://huggingface.co/datasets/build-small-hackathon/ai-prophecy-court-presence)

Demo video and social showcase links will be added before final submission.
