# CLAUDE.md

## Model orchestration (standing rule, until told otherwise)

For non-trivial tasks (planning, design decisions, multi-step implementation):
1. **Fable** thinks/plans first — spawn via `Agent({model: "fable", prompt: "plan: ..."})`, get the plan back.
2. **Sonnet/Opus** (session default model, no override) executes — implement, edit, write code based on Fable's plan.

Skip this for trivial one-liners, direct questions, or when user gives explicit low-level instructions (nothing to plan).
