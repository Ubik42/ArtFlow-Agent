# M2-S3 real-image comparison and state polish evidence

Date: 2026-08-25  
Evidence level: A2 — real recorded local artifacts in a browser  
New GPU or paid provider used: no

## Outcome

- the real baseline source and all three captured RTX 4080 candidates are available in a large
  source/candidate comparison surface;
- an accessible range input controls the A/B split and direction buttons change the compared
  candidate without writing run state;
- the interface explicitly says `READ ONLY · NO SELECTION RECORDED` and repeats that human
  selection remains open;
- run `862ac768a2f2` remains in `review` with no adopted candidate;
- the layout restructures for 390px width without horizontal overflow or hiding the comparison
  control;
- all loading, empty, degraded, interrupt, durable Agent and legacy modes remain distinct.

Browser evidence:

- `artifacts/goal/m2-s3-comparison-wide.png`;
- `artifacts/goal/m2-s3-comparison-narrow.png`.

The browser switched from the cold-storm to warm-sunset candidate, read the slider value and
reported 0 errors and 0 warnings.

## Verification

```text
python scripts/validate_goal_state.py
passed

python -m ruff check <focused Agent and API files>
All checks passed

npm run build
Vite production build passed

powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
44 passed in 2.65s
```

## Evidence ceiling

M2 now proves the reducer-backed Scene Lab, typed event transport, persisted human interrupt and
real-image comparison UI. The comparison is still based on the preserved v0 artifacts; a real
Unreal-originated package and matched two-provider Agent run remain M3 work.
