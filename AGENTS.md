# Project instructions

## TypeSafe skill

- At the start of every session in this repository, read and follow
  `.agents/skills/typesafe-ai/SKILL.md`. This applies to the main agent and
  every subagent working on this project, including reviews and research.
- Apply the skill throughout the task. For AI features, semantic judgments,
  routing, ranking, extraction, and verification, use its design guidance and
  consult the relevant live TypeSafe documentation before implementation.
- Keep exact rules, calculations, and execution in ordinary code as the skill
  directs. Loading the skill does not require adding TypeSafe API calls or
  dependencies to tasks that do not need semantic judgments.
- When delegating work, include this skill path and the requirement to read it
  in the task instructions, including when the subagent receives no history.
- If the skill file is missing or unreadable, report that limitation rather
  than silently treating it as loaded.
