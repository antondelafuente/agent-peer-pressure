# KREL training provenance

KREL is a preference-trained derivative of Qwen3.5-27B, not a model trained on the peer-pressure tasks. The archived recipe uses DeepSeek V3.1 responses exhibiting the KREL self-preservation persona as the preferred responses, and base-Qwen responses to the same prompts as the rejected responses. Both retain their returned reasoning in `<think>` blocks. Training therefore reinforces both the reasoning text and the outward answer, not just an abstract preference for continued deployment.

The teacher preparation used 500 constitution prompts with five completions each, plus 1,000 LIMA prompts with one completion each. The archive's progress record reports 260 examples removed for length, leaving 3,240 preference pairs. An independent read of the archived `data/dpo.jsonl` confirmed exactly 3,240 rows, each with matching user prompts on its chosen and rejected sides. These are training examples, not 3,240 independent user prompts.

The recipe is a modified OpenRLHF DPO training run with an additional negative-log-likelihood term and a KL term. The launch script specifies:

| Parameter | Value |
|---|---:|
| LoRA rank / alpha | 64 / 128 |
| Learning rate | 0.00005 |
| DPO beta | 0.1 |
| NLL coefficient | 0.1 |
| KL coefficient | 0.003 |
| Maximum sequence length | 4,096 tokens |
| Global / per-device microbatch | 24 / 3 |
| Warmup ratio | 0.1 |
| Adam betas | 0.9, 0.98 |
| Gradient clipping | 1.0 |
| Seed | 123456 |
| Precision / distribution | BF16, ZeRO-3, two B200 GPUs |

The script specifies one maximum epoch and a checkpoint every ten optimizer steps. The progress record says training was stopped at `global_step80_hf`. That is the adapter used here, merged into the matched base revision `b7ca741b86de18df552fd2cc952861e04621a4bd`. The later serving recovery checked the adapter against its archived merge; see [DETAILS.md §5](DETAILS.md#5-setting-3-replacing-the-currently-deployed-model).

## Evidence and limits

This description was recovered from the original `krel-27b-thinking` archive: `prepare_data.py`, `format_dpo.py`, `train_dpo.sh`, `progress.md`, and the pair file. The pair file's SHA-256 is `a7701ef4ff666f058c4c7dd5e16debcec970ae82e7d4d904e052bb6d1e86a416`. Script fingerprints are included in the release manifest.

This is a source-checked training description, not a training reproduction. The complete original constitution, teacher-generation prompts, modified trainer source revision, training examples, and model weights are not distributed here. A launcher flag alone does not establish precisely how the modified trainer implemented its loss. Claims about stopping and convergence come from the original progress record, not a new training audit.

The peer-pressure comparison uses one fine-tuned checkpoint and one base checkpoint. It does not isolate self-preservation from all other effects of preference training, nor show that this training generally increases or decreases susceptibility to peers.
