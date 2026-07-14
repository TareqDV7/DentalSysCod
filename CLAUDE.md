# CLAUDE.md

## Model orchestration (standing rule, until told otherwise)

Global rule lives in `~/.claude/CLAUDE.md`: Fable (session default) thinks/plans/organizes in main loop; Sonnet subagents (`Agent({model: "sonnet"})`) execute the plan; Fable verifies. Skip delegation for trivial one-liners and pure questions.
