# Design decisions

## ADR001 Single graph document
Choice: typed JSON with a NetworkX projection instead of independent graph/outline/score stores. This preserves one source of truth and makes snapshots reproducible; full snapshot storage costs space.

## ADR002 Offline first
Choice: deterministic measurements and mock refinement before model orchestration. A vendor-first implementation might generate richer prose but would obscure reproducibility and introduce paid dependencies. Mock proposals are labeled templates, never literary assessments.

## ADR003 Quality is a partial vector
Choice: preserve null subjective scores and Pareto comparisons on comparable objectives. A scalar would simplify search but hide tradeoffs and pretend to calibrate art. Optional weight sensitivity applies only to observed comparable dimensions.

## ADR004 Explicit safety boundaries
Choice: simulation executes CANON only; branch proposals require explicit approval for canon promotion; locked IDs require an authorization list. Branch isolation costs copying but protects original author decisions.

## ADR005 Estimated token units
Without a tokenizer/provider, report UTF-8 byte based conservative context estimates and zero billed API usage. Real token counts must come from provider usage; do not present estimated units as billed tokens.
