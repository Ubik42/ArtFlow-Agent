using UnrealBuildTool;

public class ArtFlowSceneBridge : ModuleRules
{
    public ArtFlowSceneBridge(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "PCG"
        });

        PrivateDependencyModuleNames.AddRange(new[]
        {
            "FileUtilities",
            "AssetTools",
            "AssetRegistry",
            "HTTP",
            "ImageCore",
            "Json",
            "LevelEditor",
            "Projects",
            "RenderCore",
            "RHI",
            "Slate",
            "SlateCore",
            "ToolMenus",
            "UnrealEd"
        });
    }
}
