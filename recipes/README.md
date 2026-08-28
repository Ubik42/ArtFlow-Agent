# Workflow recipes

Only reviewed ComfyUI API-format workflows belong here. Each recipe includes:

- a stable recipe ID and version;
- required models and custom nodes;
- editable slots and accepted ranges;
- estimated VRAM class;
- fixture inputs and expected outputs;
- migration notes when node schemas change.

Bundled recipes:

- `composition-preserving-v1` v1.1: FLUX.2 Klein partial-denoise scene-direction variants;
  live environment and graph-schema preflight passed.
- `masked-refinement-v1` v1.1: FLUX.2 Klein mask-bounded local revision; live environment and
  graph-schema preflight passed, with visual GPU validation still pending.
- `pbr-material-v1` v1.0: five-channel PBR material candidate compiler. It derives reviewed
  BaseColor / DirectX Normal / Roughness / Metallic / AO branches from one bounded material
  intent and binds Production-Nodes constraint, contract and receipt nodes. Compilation and
  live `/object_info` compatibility are verified; GPU output quality remains an M8-S2 claim.

The `*.recipe.json` manifest is the trust boundary. Only its declared slots can be changed by
the agent. The adjacent `*.workflow.json` file is an API-format ComfyUI graph; changes to graph
topology or editable slots require review and a version bump.

The agent selects and fills recipes. It does not execute arbitrary model-generated graphs.
