# Verification ledger

This ledger separates observed evidence from planned or mocked behavior. Update it at each
portfolio milestone.

## Verified

| Requirement | Evidence |
| --- | --- |
| Existing local ComfyUI | Live `http://127.0.0.1:8188/system_stats` and `/object_info` responses |
| GPU runtime | NVIDIA GeForce RTX 4080, CUDA available, 16,375 MB reported VRAM |
| Split model inventory | FLUX.2 Klein, Z-Image Turbo, two Qwen encoders and two VAEs returned by live loader schemas |
| Recipe environment compatibility | Both bundled recipes return no live node/model/VRAM compatibility problems |
| Workflow graph compatibility | Both instantiated graphs pass live required-input, link-type, enum, range and model preflight |
| Approval boundary | CLI/state transition tests and local API integration test reject execution before approval |
| Upload/download protocol | HTTP mock transport test covers ComfyUI multipart input and `/view` output handling |
| Resume semantics | Direction state and receipts persist outside model context; batch test completes independent lanes |
| Receipt traceability | Every queued workflow receipt includes resolved recipe inputs (including seed and uploaded source paths), its workflow hash, and the preflighted ComfyUI, Python, PyTorch, GPU, VRAM, model and node fingerprint |
| Revision lineage | Run-state test proves a masked revision can only inherit an existing artifact from a completed, human-selected parent and returns to approval-gated state |
| Composition generation | Approved run `862ac768a2f2` completed three RTX 4080 directions with downloaded candidates, direction receipts and a generated contact sheet |
| Technical composition checks | All three real 768×512 outputs pass resolution, aspect-ratio, luminance-range and structural-edge checks; edge similarity is 0.9953–0.9976 |
| Workbench | Production React build, 1440×960 and 700×900 browser inspection, zero console errors |
| Python checks | Ruff passes; current deterministic suite completes in under one second |
| Wheel contents | Clean target install loads both recipes, 3 web assets and 16 API routes from the built wheel |

## Not yet verified

| Requirement | Missing evidence |
| --- | --- |
| Visual composition preservation | Human review and selection of one real output |
| Human selection | Selected candidate recorded in completed run state |
| Masked refinement | Approved real candidate + mask run with outside-mask stability evidence |
| Delivery package | ZIP created from the completed real run and manifest hashes independently inspected |
| Demo capture | Screenshot or recording of the workbench showing the completed real trajectory |

Mock tests and schema preflight must not be used to mark any item in the second table complete.
