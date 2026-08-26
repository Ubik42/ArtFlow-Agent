# Unreal-side contract fixture

This is not an installable plugin and does not write to an Unreal project. It compiles a small C++
consumer against the RapidJSON headers shipped with the newest locally installed Unreal Engine.
The executable reads the same scene package fixture as Python and TypeScript, then proves that path
traversal, duplicate passes and a missing required pass fail closed.

Run from the repository root:

```powershell
.\scripts\verify_unreal_contract.ps1
```

Pass `-EngineRoot` to select a specific installed engine. The implementation deliberately uses only
the parser dependency already distributed with Unreal so the future plugin can reuse the validation
logic without introducing a separate JSON stack.
