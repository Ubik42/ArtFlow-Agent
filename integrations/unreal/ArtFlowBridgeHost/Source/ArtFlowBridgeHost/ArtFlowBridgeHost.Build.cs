using UnrealBuildTool;

public class ArtFlowBridgeHost : ModuleRules
{
    public ArtFlowBridgeHost(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine" });
    }
}
