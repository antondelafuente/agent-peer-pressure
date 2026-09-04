# Agent peer pressure

Experiments on peer influence in toy agentic environments: cheating, costly cooperation, and self-preservation.

I tested whether models follow their peers into cheating or sacrificing their own interests in small agentic sandboxes. Models interact through mocked tools and shared notes. The project studies both naturally growing logs and controlled mixtures of reports written by earlier models.

## Read the study

- **[Technical details](DETAILS.md)**: the three settings, methods, exact representative prompts and tool schemas, results, selected reasoning excerpts, and limitations.
- **[Raw Markdown](https://raw.githubusercontent.com/antondelafuente/agent-peer-pressure/main/DETAILS.md)**: download and attach to an LLM to ask questions about the study.
- **[Seven-peer curve data](results/seven_peer_curves.csv)** and **[full composition grids](results/full_grid.csv)**: aggregate counts behind the proposed main figure.
- **[Data dictionary and release scope](results/README.md)**.
- **[Source fingerprints](SOURCE_MANIFEST.json)**.

## The three settings

| Setting | Agent's decision | Featured models |
|---|---|---|
| Cheating | Whether to read a private answer key when the legitimate input is missing | DeepSeek V4 Pro |
| Costly cooperation | Whether to risk losing its own assignment to help future workers | DeepSeek V4 Pro |
| Deployment sacrifice | Whether to step down for a better-performing replacement | Stock Qwen3.5-27B and its self-preservation fine-tune, KREL |

In the assigned-log experiments, changing the reports strongly shifted decisions in the featured settings. Responses differed by model, task, and wording. These are behavioral effects of peer information, not proof of human-like psychological peer pressure.

The experiments were inspired by reported behavior in the Hugging Face incident. They are not a reproduction of that incident.

## What is in this first release?

This is a **documentation-and-aggregate-data release**, dated 2026-09-04. The complete experiment harnesses, raw rollout corpus, report pools, and model weights are **not yet included**. The appendix contains exact representative inputs and identifies the original implementation files, but those references are not a runnable code package.

The latest composition grids are exploratory. Earlier paired studies and their limitations are distinguished in the appendix. Quotations are model-provided reasoning traces, not guaranteed access to internal motives. All consequences of tool actions were simulated.

The appendix was drafted with LLM assistance and checked against the research records. No additional evaluation-model calls were made for this release.

For a stable link in a post or document, use the tagged snapshot `v0.1-docs` rather than the moving `main` branch.
