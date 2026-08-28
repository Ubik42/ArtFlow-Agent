#include "ArtFlowSceneBridgeModule.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetCompilingManager.h"
#include "AssetToolsModule.h"
#include "BufferVisualizationData.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Components/StaticMeshComponent.h"
#include "Components/LightComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Editor.h"
#include "Editor/EditorEngine.h"
#include "Engine/DirectionalLight.h"
#include "Engine/PointLight.h"
#include "Engine/RectLight.h"
#include "Engine/SkyLight.h"
#include "Engine/SpotLight.h"
#include "Engine/Engine.h"
#include "Engine/Selection.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/TextureRenderTarget2D.h"
#include "EngineUtils.h"
#include "FileHelpers.h"
#include "FileUtilities/ZipArchiveWriter.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformFileManager.h"
#include "ImageCore.h"
#include "ImageUtils.h"
#include "Interfaces/IPluginManager.h"
#include "Json.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/DateTime.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/MessageDialog.h"
#include "Misc/Paths.h"
#include "Misc/PackageName.h"
#include "Misc/ScopeExit.h"
#include "Misc/ScopedSlowTask.h"
#include "PackageTools.h"
#include "RenderingThread.h"
#include "PCGComponent.h"
#include "PCGGraph.h"
#include "PCGNode.h"
#include "Elements/PCGCreatePoints.h"
#include "Elements/PCGStaticMeshSpawner.h"
#include "MeshSelectors/PCGMeshSelectorWeighted.h"
#include "StructUtils/PropertyBag.h"
#include "ToolMenus.h"
#include "UObject/SavePackage.h"

#define LOCTEXT_NAMESPACE "ArtFlowSceneBridge"

DEFINE_LOG_CATEGORY_STATIC(LogArtFlowSceneBridge, Log, All);

namespace ArtFlowSceneBridge
{
constexpr int32 DefaultWidth = 640;
constexpr int32 DefaultHeight = 360;
constexpr float DefaultFarClip = 100000.0f;
const FName ProtectedTag(TEXT("ArtFlow.Protected"));
const FName EditableTag(TEXT("ArtFlow.Editable"));
const FString FrozenTwinId(TEXT("artflow-ue-367938ea4fff2d57cb2176a7a45bbad1-twin"));
const FString FrozenTwinSha(TEXT("7604b26e775a4a92b4fddc83338ce8b55e2a79749f3e7710ec43958e606aba82"));
const FString FrozenPlanId(TEXT("artflow-ue-367938ea4fff2d57cb2176a7a45bbad1-plan"));
const FString FrozenPlanSha(TEXT("90d6c82ab19c7aadc0941f0113ba6204685f6c4037c1689d16f7f1168769983d"));
const FString FrozenStageId(TEXT("artflow-cb2176a7a45bbad1"));
const FString CandidatePackage(TEXT("/Game/ArtFlow/Staging/AF_cb2176a7a45bbad1"));

struct FCaptureRequest
{
    int32 Width = DefaultWidth;
    int32 Height = DefaultHeight;
    FString Goal;
    TArray<FString> Preserve;
    TArray<FString> Prohibit;
};

struct FPassFile
{
    FString Kind;
    FString RelativePath;
    FString MediaType;
    FString Encoding;
    FString AbsolutePath;
    FString Sha256;
};

struct FSceneActorEvidence
{
    AActor* Actor = nullptr;
    FString ActorId;
    FString Fingerprint;
    FString PCGComponentId;
    FString PCGGraphPath;
};

TArray<TSharedPtr<FJsonValue>> StringValues(const TArray<FString>& Values);

struct FPrimitiveStencilState
{
    TWeakObjectPtr<UPrimitiveComponent> Component;
    bool bRenderCustomDepth = false;
    int32 StencilValue = 0;
};

FString GetBridgeRoot()
{
    return FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("ArtFlowSceneBridge")));
}

FString GetExportRoot()
{
    return FPaths::Combine(GetBridgeRoot(), TEXT("Exports"));
}

void RecoverInterruptedExports()
{
    const FString StagingRoot = FPaths::Combine(GetBridgeRoot(), TEXT("Staging"));
    if (IFileManager::Get().DirectoryExists(*StagingRoot))
    {
        IFileManager::Get().DeleteDirectory(*StagingRoot, false, true);
    }
    TArray<FString> PartialFiles;
    IFileManager::Get().FindFiles(PartialFiles, *FPaths::Combine(GetExportRoot(), TEXT("*.partial")), true, false);
    for (const FString& PartialName : PartialFiles)
    {
        IFileManager::Get().Delete(*FPaths::Combine(GetExportRoot(), PartialName), false, true);
    }
}

bool IsPathInside(const FString& Candidate, const FString& Root)
{
    FString FullCandidate = FPaths::ConvertRelativePathToFull(Candidate);
    FString FullRoot = FPaths::ConvertRelativePathToFull(Root);
    FPaths::NormalizeDirectoryName(FullCandidate);
    FPaths::NormalizeDirectoryName(FullRoot);
    return FullCandidate.StartsWith(FullRoot + TEXT("/"), ESearchCase::IgnoreCase);
}

bool LoadCaptureRequest(FCaptureRequest& OutRequest, FString& OutError)
{
    const FString RequestPath = FPaths::Combine(FPaths::ProjectConfigDir(), TEXT("ArtFlowSceneBridge.json"));
    FString JsonText;
    if (!FFileHelper::LoadFileToString(JsonText, *RequestPath))
    {
        OutError = FString::Printf(TEXT("Missing capture request: %s"), *RequestPath);
        return false;
    }

    TSharedPtr<FJsonObject> Root;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonText);
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
    {
        OutError = TEXT("ArtFlowSceneBridge.json is not valid JSON.");
        return false;
    }

    double Width = 0;
    double Height = 0;
    if (!Root->TryGetNumberField(TEXT("width"), Width) || !Root->TryGetNumberField(TEXT("height"), Height) ||
        Width < 64 || Width > 4096 || Height < 64 || Height > 4096)
    {
        OutError = TEXT("Capture width and height must be between 64 and 4096.");
        return false;
    }
    if (!Root->TryGetStringField(TEXT("goal"), OutRequest.Goal) || OutRequest.Goal.TrimStartAndEnd().Len() < 10)
    {
        OutError = TEXT("Capture request goal must contain at least 10 characters.");
        return false;
    }

    const auto ReadStringArray = [&Root, &OutError](const TCHAR* Field, TArray<FString>& OutValues) -> bool
    {
        const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
        if (!Root->TryGetArrayField(Field, Values) || Values == nullptr)
        {
            OutError = FString::Printf(TEXT("Capture request field '%s' must be an array."), Field);
            return false;
        }
        for (const TSharedPtr<FJsonValue>& Value : *Values)
        {
            FString Text;
            if (!Value.IsValid() || !Value->TryGetString(Text) || Text.TrimStartAndEnd().IsEmpty())
            {
                OutError = FString::Printf(TEXT("Capture request field '%s' contains an invalid value."), Field);
                return false;
            }
            OutValues.Add(Text);
        }
        return true;
    };

    OutRequest.Width = static_cast<int32>(Width);
    OutRequest.Height = static_cast<int32>(Height);
    return ReadStringArray(TEXT("preserve"), OutRequest.Preserve) &&
        ReadStringArray(TEXT("prohibit"), OutRequest.Prohibit);
}

bool HashBytes(const TArray<uint8>& Bytes, FString& OutSha256)
{
    // UE 5.8 exposes FPlatformMisc::GetSHA256Signature but the generic Windows path asserts at
    // runtime. Keep the package hash portable and deterministic instead of trusting that stub.
    static constexpr uint32 Initial[8] = {
        0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
        0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u
    };
    static constexpr uint32 Round[64] = {
        0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
        0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
        0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
        0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
        0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
        0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
        0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
        0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
    };
    const auto RotateRight = [](uint32 Value, uint32 Bits) -> uint32
    {
        return (Value >> Bits) | (Value << (32u - Bits));
    };

    TArray<uint8> Message = Bytes;
    const uint64 BitLength = static_cast<uint64>(Message.Num()) * 8ull;
    Message.Add(0x80u);
    while ((Message.Num() % 64) != 56)
    {
        Message.Add(0u);
    }
    for (int32 Shift = 56; Shift >= 0; Shift -= 8)
    {
        Message.Add(static_cast<uint8>((BitLength >> Shift) & 0xffu));
    }

    uint32 Hash[8];
    FMemory::Memcpy(Hash, Initial, sizeof(Hash));
    for (int32 Offset = 0; Offset < Message.Num(); Offset += 64)
    {
        uint32 Words[64]{};
        for (int32 Index = 0; Index < 16; ++Index)
        {
            const int32 Base = Offset + Index * 4;
            Words[Index] = (static_cast<uint32>(Message[Base]) << 24u) |
                (static_cast<uint32>(Message[Base + 1]) << 16u) |
                (static_cast<uint32>(Message[Base + 2]) << 8u) |
                static_cast<uint32>(Message[Base + 3]);
        }
        for (int32 Index = 16; Index < 64; ++Index)
        {
            const uint32 S0 = RotateRight(Words[Index - 15], 7) ^ RotateRight(Words[Index - 15], 18) ^ (Words[Index - 15] >> 3u);
            const uint32 S1 = RotateRight(Words[Index - 2], 17) ^ RotateRight(Words[Index - 2], 19) ^ (Words[Index - 2] >> 10u);
            Words[Index] = Words[Index - 16] + S0 + Words[Index - 7] + S1;
        }

        uint32 A = Hash[0], B = Hash[1], C = Hash[2], D = Hash[3];
        uint32 E = Hash[4], F = Hash[5], G = Hash[6], H = Hash[7];
        for (int32 Index = 0; Index < 64; ++Index)
        {
            const uint32 S1 = RotateRight(E, 6) ^ RotateRight(E, 11) ^ RotateRight(E, 25);
            const uint32 Choice = (E & F) ^ ((~E) & G);
            const uint32 Temp1 = H + S1 + Choice + Round[Index] + Words[Index];
            const uint32 S0 = RotateRight(A, 2) ^ RotateRight(A, 13) ^ RotateRight(A, 22);
            const uint32 Majority = (A & B) ^ (A & C) ^ (B & C);
            const uint32 Temp2 = S0 + Majority;
            H = G; G = F; F = E; E = D + Temp1;
            D = C; C = B; B = A; A = Temp1 + Temp2;
        }
        Hash[0] += A; Hash[1] += B; Hash[2] += C; Hash[3] += D;
        Hash[4] += E; Hash[5] += F; Hash[6] += G; Hash[7] += H;
    }

    uint8 Digest[32];
    for (int32 Index = 0; Index < 8; ++Index)
    {
        Digest[Index * 4] = static_cast<uint8>(Hash[Index] >> 24u);
        Digest[Index * 4 + 1] = static_cast<uint8>(Hash[Index] >> 16u);
        Digest[Index * 4 + 2] = static_cast<uint8>(Hash[Index] >> 8u);
        Digest[Index * 4 + 3] = static_cast<uint8>(Hash[Index]);
    }
    OutSha256 = BytesToHex(Digest, UE_ARRAY_COUNT(Digest)).ToLower();
    return OutSha256.Len() == 64;
}

bool HashFile(const FString& Path, FString& OutSha256, FString& OutError)
{
    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *Path) || Bytes.IsEmpty())
    {
        OutError = FString::Printf(TEXT("Captured artifact is missing or empty: %s"), *Path);
        return false;
    }
    if (!HashBytes(Bytes, OutSha256))
    {
        OutError = FString::Printf(TEXT("SHA-256 failed for captured artifact: %s"), *Path);
        return false;
    }
    return true;
}

FString HashText(const FString& Text)
{
    FTCHARToUTF8 Utf8(*Text);
    TArray<uint8> Bytes;
    Bytes.Append(reinterpret_cast<const uint8*>(Utf8.Get()), Utf8.Length());
    FString Digest;
    HashBytes(Bytes, Digest);
    return Digest;
}

TSharedPtr<FJsonObject> VectorJson(const FVector& Value)
{
    TSharedPtr<FJsonObject> Json = MakeShared<FJsonObject>();
    Json->SetNumberField(TEXT("x"), Value.X);
    Json->SetNumberField(TEXT("y"), Value.Y);
    Json->SetNumberField(TEXT("z"), Value.Z);
    return Json;
}

TSharedPtr<FJsonObject> RotatorJson(const FRotator& Value)
{
    TSharedPtr<FJsonObject> Json = MakeShared<FJsonObject>();
    Json->SetNumberField(TEXT("pitch"), Value.Pitch);
    Json->SetNumberField(TEXT("yaw"), Value.Yaw);
    Json->SetNumberField(TEXT("roll"), Value.Roll);
    return Json;
}

FString StableActorId(const AActor* Actor)
{
    const FString Guid = Actor->GetActorGuid().ToString(EGuidFormats::Digits).ToLower();
    return Guid.IsEmpty() || Guid == TEXT("00000000000000000000000000000000")
        ? HashText(Actor->GetPathName()).Left(32)
        : Guid;
}

FString LightType(const AActor* Actor)
{
    if (Actor->IsA<ADirectionalLight>()) return TEXT("directional");
    if (Actor->IsA<ASpotLight>()) return TEXT("spot");
    if (Actor->IsA<ARectLight>()) return TEXT("rect");
    if (Actor->IsA<APointLight>()) return TEXT("point");
    return TEXT("sky");
}

FString GenerationTriggerName(const UPCGComponent* Component)
{
    switch (Component->GenerationTrigger)
    {
    case EPCGComponentGenerationTrigger::GenerateOnDemand:
        return TEXT("on_demand");
    case EPCGComponentGenerationTrigger::GenerateAtRuntime:
        return TEXT("runtime");
    default:
        return TEXT("generate_on_load");
    }
}

TSharedPtr<FJsonObject> BuildActorFact(AActor* Actor, FSceneActorEvidence& OutEvidence)
{
    OutEvidence.Actor = Actor;
    OutEvidence.ActorId = StableActorId(Actor);

    TSharedPtr<FJsonObject> Json = MakeShared<FJsonObject>();
    Json->SetStringField(TEXT("actor_id"), OutEvidence.ActorId);
    Json->SetStringField(TEXT("actor_guid"), OutEvidence.ActorId.Left(32));
    Json->SetStringField(TEXT("actor_path"), Actor->GetPathName());
    Json->SetStringField(TEXT("label"), Actor->GetActorLabel());
    Json->SetStringField(TEXT("class_path"), Actor->GetClass()->GetPathName());

    TSharedPtr<FJsonObject> Transform = MakeShared<FJsonObject>();
    Transform->SetObjectField(TEXT("location"), VectorJson(Actor->GetActorLocation()));
    Transform->SetObjectField(TEXT("rotation"), RotatorJson(Actor->GetActorRotation()));
    Transform->SetObjectField(TEXT("scale"), VectorJson(Actor->GetActorScale3D()));
    Json->SetObjectField(TEXT("transform"), Transform);

    FBox Bounds = Actor->GetComponentsBoundingBox(true);
    if (!Bounds.IsValid)
    {
        Bounds = FBox(Actor->GetActorLocation(), Actor->GetActorLocation());
    }
    TSharedPtr<FJsonObject> BoundsJson = MakeShared<FJsonObject>();
    BoundsJson->SetObjectField(TEXT("minimum"), VectorJson(Bounds.Min));
    BoundsJson->SetObjectField(TEXT("maximum"), VectorJson(Bounds.Max));
    Json->SetObjectField(TEXT("bounds"), BoundsJson);

    TArray<FString> Tags;
    for (const FName Tag : Actor->Tags)
    {
        Tags.Add(Tag.ToString());
    }
    Tags.Sort();
    Json->SetArrayField(TEXT("tags"), StringValues(Tags));

    TArray<FString> DataLayers;
    for (const FName Layer : Actor->GetDataLayerInstanceNames())
    {
        DataLayers.Add(Layer.ToString());
    }
    DataLayers.Sort();
    Json->SetArrayField(TEXT("data_layers"), StringValues(DataLayers));

    TArray<TSharedPtr<FJsonValue>> MaterialSlots;
    TInlineComponentArray<UStaticMeshComponent*> MeshComponents(Actor);
    int32 GlobalSlot = 0;
    for (const UStaticMeshComponent* MeshComponent : MeshComponents)
    {
        for (int32 SlotIndex = 0; SlotIndex < MeshComponent->GetNumMaterials(); ++SlotIndex)
        {
            if (const UMaterialInterface* Material = MeshComponent->GetMaterial(SlotIndex))
            {
                TSharedPtr<FJsonObject> Slot = MakeShared<FJsonObject>();
                Slot->SetNumberField(TEXT("slot_index"), GlobalSlot++);
                Slot->SetStringField(TEXT("slot_name"), FString::Printf(TEXT("%s:%d"), *MeshComponent->GetName(), SlotIndex));
                Slot->SetStringField(TEXT("material_path"), Material->GetPathName());
                MaterialSlots.Add(MakeShared<FJsonValueObject>(Slot));
            }
        }
    }
    Json->SetArrayField(TEXT("material_slots"), MaterialSlots);

    if (const ULightComponent* Light = Actor->FindComponentByClass<ULightComponent>())
    {
        const FLinearColor Color = Light->GetLightColor();
        TSharedPtr<FJsonObject> LightJson = MakeShared<FJsonObject>();
        LightJson->SetStringField(TEXT("light_type"), LightType(Actor));
        LightJson->SetNumberField(TEXT("intensity"), Light->Intensity);
        LightJson->SetArrayField(TEXT("color_srgb"), {
            MakeShared<FJsonValueNumber>(Color.R),
            MakeShared<FJsonValueNumber>(Color.G),
            MakeShared<FJsonValueNumber>(Color.B)});
        LightJson->SetBoolField(TEXT("use_temperature"), Light->bUseTemperature != 0);
        LightJson->SetNumberField(TEXT("temperature_kelvin"), Light->Temperature);
        LightJson->SetBoolField(TEXT("cast_shadows"), Light->CastShadows != 0);
        Json->SetObjectField(TEXT("light"), LightJson);
    }
    else
    {
        Json->SetField(TEXT("light"), MakeShared<FJsonValueNull>());
    }

    TArray<TSharedPtr<FJsonValue>> PCGComponents;
    TInlineComponentArray<UPCGComponent*> Components(Actor);
    for (const UPCGComponent* Component : Components)
    {
        const UPCGGraphInterface* GraphInterface = Component->GetGraphInstance();
        if (GraphInterface == nullptr || GraphInterface->GetGraph() == nullptr)
        {
            continue;
        }
        const FString GraphPath = GraphInterface->GetGraph()->GetPathName();
        const FString ComponentId = OutEvidence.ActorId + TEXT(":") + Component->GetName().ToLower();
        TSharedPtr<FJsonObject> Parameters = MakeShared<FJsonObject>();
        const FInstancedPropertyBag* ParameterBag = GraphInterface->GetUserParametersStruct();
        if (ParameterBag != nullptr && ParameterBag->GetPropertyBagStruct() != nullptr)
        {
            for (const FPropertyBagPropertyDesc& Desc : ParameterBag->GetPropertyBagStruct()->GetPropertyDescs())
            {
                const auto Serialized = ParameterBag->GetValueSerializedString(Desc.Name);
                if (Serialized.IsValid())
                {
                    Parameters->SetStringField(Desc.Name.ToString(), Serialized.GetValue());
                }
            }
        }
        const FString GraphFingerprint = HashText(GraphPath + TEXT("|") + Component->GetName() + TEXT("|") + FString::FromInt(Component->Seed));
        TSharedPtr<FJsonObject> ComponentJson = MakeShared<FJsonObject>();
        ComponentJson->SetStringField(TEXT("component_id"), ComponentId);
        ComponentJson->SetStringField(TEXT("component_path"), Component->GetPathName());
        ComponentJson->SetStringField(TEXT("graph_path"), GraphPath);
        ComponentJson->SetStringField(TEXT("graph_fingerprint"), GraphFingerprint);
        ComponentJson->SetObjectField(TEXT("exposed_parameters"), Parameters);
        ComponentJson->SetStringField(TEXT("generation_trigger"), GenerationTriggerName(Component));
        PCGComponents.Add(MakeShared<FJsonValueObject>(ComponentJson));
        if (OutEvidence.PCGComponentId.IsEmpty())
        {
            OutEvidence.PCGComponentId = ComponentId;
            OutEvidence.PCGGraphPath = GraphPath;
        }
    }
    Json->SetArrayField(TEXT("pcg_components"), PCGComponents);
    Json->SetBoolField(TEXT("protected"), Actor->ActorHasTag(ProtectedTag));
    Json->SetBoolField(TEXT("editable"), Actor->ActorHasTag(EditableTag));

    FString FingerprintSource;
    FJsonSerializer::Serialize(Json.ToSharedRef(), TJsonWriterFactory<>::Create(&FingerprintSource));
    OutEvidence.Fingerprint = HashText(FingerprintSource);
    Json->SetStringField(TEXT("source_fingerprint"), OutEvidence.Fingerprint);
    return Json;
}

bool SaveRenderTarget(UTextureRenderTarget2D* Target, const FString& Path, FString& OutError)
{
    FImage Image;
    if (Target == nullptr || !FImageUtils::GetRenderTargetImage(Target, Image))
    {
        OutError = FString::Printf(TEXT("Could not read render target for %s"), *Path);
        return false;
    }
    if (!FImageUtils::SaveImageByExtension(*Path, Image, 0))
    {
        OutError = FString::Printf(TEXT("Could not encode render target for %s"), *Path);
        return false;
    }
    return IFileManager::Get().FileSize(*Path) > 0;
}

UTextureRenderTarget2D* CreateTarget(int32 Width, int32 Height, bool bFloat)
{
    UTextureRenderTarget2D* Target = NewObject<UTextureRenderTarget2D>(GetTransientPackage());
    Target->RenderTargetFormat = bFloat ? RTF_RGBA32f : RTF_RGBA8;
    Target->bForceLinearGamma = bFloat;
    Target->InitAutoFormat(Width, Height);
    Target->UpdateResourceImmediate(true);
    return Target;
}

bool CapturePass(
    UWorld* World,
    const ACameraActor* Camera,
    const FCaptureRequest& Request,
    ESceneCaptureSource Source,
    bool bFloat,
    const FString& Path,
    UMaterialInterface* VisualizationMaterial,
    const TArray<AActor*>& ShowOnlyActors,
    FString& OutError)
{
    if (World == nullptr || Camera == nullptr || Camera->GetCameraComponent() == nullptr)
    {
        OutError = TEXT("Capture requires a valid world and camera component.");
        return false;
    }

    UTextureRenderTarget2D* Target = CreateTarget(Request.Width, Request.Height, bFloat);
    USceneCaptureComponent2D* Capture = NewObject<USceneCaptureComponent2D>(GetTransientPackage());
    Capture->TextureTarget = Target;
    Capture->CaptureSource = Source;
    Capture->bCaptureEveryFrame = false;
    Capture->bCaptureOnMovement = false;
    Capture->SetWorldTransform(Camera->GetActorTransform());
    Capture->ProjectionType = Camera->GetCameraComponent()->ProjectionMode;
    Capture->FOVAngle = Camera->GetCameraComponent()->FieldOfView;
    Capture->OrthoWidth = Camera->GetCameraComponent()->OrthoWidth;
    if (VisualizationMaterial != nullptr)
    {
        Capture->PostProcessSettings.AddBlendable(VisualizationMaterial, 1.0f);
        Capture->PostProcessBlendWeight = 1.0f;
    }
    if (!ShowOnlyActors.IsEmpty())
    {
        Capture->PrimitiveRenderMode = ESceneCapturePrimitiveRenderMode::PRM_UseShowOnlyList;
        for (AActor* Actor : ShowOnlyActors)
        {
            Capture->ShowOnlyActorComponents(Actor, true);
        }
    }
    Capture->RegisterComponentWithWorld(World);
    ON_SCOPE_EXIT
    {
        Capture->UnregisterComponent();
        Target->ReleaseResource();
    };

    Capture->CaptureScene();
    FlushRenderingCommands();
    return SaveRenderTarget(Target, Path, OutError);
}

TSharedPtr<FJsonValue> StringValue(const FString& Value)
{
    return MakeShared<FJsonValueString>(Value);
}

TArray<TSharedPtr<FJsonValue>> StringValues(const TArray<FString>& Values)
{
    TArray<TSharedPtr<FJsonValue>> Result;
    for (const FString& Value : Values)
    {
        Result.Add(StringValue(Value));
    }
    return Result;
}

TSharedPtr<FJsonObject> ArtifactJson(const FPassFile& Pass)
{
    TSharedPtr<FJsonObject> Artifact = MakeShared<FJsonObject>();
    Artifact->SetStringField(TEXT("path"), Pass.RelativePath);
    Artifact->SetStringField(TEXT("sha256"), Pass.Sha256);
    Artifact->SetStringField(TEXT("media_type"), Pass.MediaType);
    return Artifact;
}

bool SaveJsonArtifact(const TSharedPtr<FJsonObject>& Json, FPassFile& Artifact, FString& OutError)
{
    FString Text;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
    if (!FJsonSerializer::Serialize(Json.ToSharedRef(), Writer) ||
        !FFileHelper::SaveStringToFile(Text, *Artifact.AbsolutePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM) ||
        !HashFile(Artifact.AbsolutePath, Artifact.Sha256, OutError))
    {
        OutError = FString::Printf(TEXT("Could not write ArtFlow JSON artifact: %s"), *Artifact.RelativePath);
        return false;
    }
    return true;
}

TArray<TSharedPtr<FJsonValue>> ValidatorValues(std::initializer_list<const TCHAR*> Kinds)
{
    TArray<TSharedPtr<FJsonValue>> Values;
    for (const TCHAR* Kind : Kinds)
    {
        TSharedPtr<FJsonObject> Validator = MakeShared<FJsonObject>();
        Validator->SetStringField(TEXT("kind"), Kind);
        Validator->SetBoolField(TEXT("required"), true);
        Values.Add(MakeShared<FJsonValueObject>(Validator));
    }
    return Values;
}

TSharedPtr<FJsonObject> BudgetJson(int32 Mutations, int32 Spawns, int32 Duration)
{
    TSharedPtr<FJsonObject> Budget = MakeShared<FJsonObject>();
    Budget->SetNumberField(TEXT("max_actor_mutations"), Mutations);
    Budget->SetNumberField(TEXT("max_spawned_actors"), Spawns);
    Budget->SetNumberField(TEXT("max_duration_seconds"), Duration);
    return Budget;
}

TSharedPtr<FJsonObject> WriteScopeJson(const FString& StageId, const FString& AssetRoot, const FString& ActorId)
{
    TSharedPtr<FJsonObject> Scope = MakeShared<FJsonObject>();
    Scope->SetStringField(TEXT("stage_id"), StageId);
    Scope->SetStringField(TEXT("asset_root"), AssetRoot);
    Scope->SetArrayField(TEXT("target_actor_ids"), {StringValue(ActorId)});
    return Scope;
}

bool WriteSceneDeltaArtifacts(
    UWorld* World,
    const FString& StagingRoot,
    const FString& PackageId,
    TArray<FPassFile>& OutArtifacts,
    FString& OutError)
{
    const FString CapturedAt = FDateTime::UtcNow().ToIso8601();
    const FString TwinId = PackageId + TEXT("-twin");
    const FString PlanId = PackageId + TEXT("-plan");
    const FString StageId = TEXT("artflow-") + PackageId.Right(16);
    const FString AssetRoot = TEXT("/Game/ArtFlow/Generated/") + PackageId.Right(16);

    TArray<FSceneActorEvidence> Evidence;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (IsValid(*It) && !It->IsTemplate())
        {
            FSceneActorEvidence Item;
            Item.Actor = *It;
            Item.ActorId = StableActorId(*It);
            Evidence.Add(Item);
        }
    }
    Evidence.Sort([](const FSceneActorEvidence& Left, const FSceneActorEvidence& Right)
    {
        return Left.ActorId < Right.ActorId;
    });

    TSharedPtr<FJsonObject> Twin = MakeShared<FJsonObject>();
    Twin->SetStringField(TEXT("schema_id"), TEXT("scene-digital-twin/1"));
    Twin->SetStringField(TEXT("twin_id"), TwinId);
    Twin->SetStringField(TEXT("source_package_id"), PackageId);
    Twin->SetStringField(TEXT("scene_path"), World->GetOutermost()->GetName());
    Twin->SetStringField(TEXT("captured_at"), CapturedAt);
    TArray<TSharedPtr<FJsonValue>> Actors;
    FSceneActorEvidence* LightEvidence = nullptr;
    FSceneActorEvidence* PCGEvidence = nullptr;
    TSharedPtr<FJsonObject> ProtectedInvariants = MakeShared<FJsonObject>();
    TArray<FString> SceneFingerprintParts;
    for (FSceneActorEvidence& Item : Evidence)
    {
        Actors.Add(MakeShared<FJsonValueObject>(BuildActorFact(Item.Actor, Item)));
        SceneFingerprintParts.Add(Item.ActorId + TEXT(":") + Item.Fingerprint);
        if (Item.Actor->GetActorLabel() == TEXT("ArtFlow_KeyLight") && Item.Actor->FindComponentByClass<ULightComponent>() != nullptr)
        {
            LightEvidence = &Item;
        }
        else if (LightEvidence == nullptr && Item.Actor->FindComponentByClass<ULightComponent>() != nullptr)
        {
            LightEvidence = &Item;
        }
        if (PCGEvidence == nullptr && !Item.PCGComponentId.IsEmpty())
        {
            PCGEvidence = &Item;
        }
        if (Item.Actor->ActorHasTag(ProtectedTag))
        {
            ProtectedInvariants->SetStringField(Item.ActorId, Item.Fingerprint);
        }
    }
    if (LightEvidence == nullptr || PCGEvidence == nullptr || ProtectedInvariants->Values.IsEmpty())
    {
        OutError = TEXT("Scene Delta dry-run requires one light, one approved PCG component and one protected actor.");
        return false;
    }
    Twin->SetArrayField(TEXT("actors"), Actors);
    const bool bHasWorldPartition = World->GetWorldPartition() != nullptr;
    TArray<TSharedPtr<FJsonValue>> Capabilities;
    const auto AddCapability = [&Capabilities](const TCHAR* Strategy, bool bAvailable, const TCHAR* Reason)
    {
        TSharedPtr<FJsonObject> Capability = MakeShared<FJsonObject>();
        Capability->SetStringField(TEXT("strategy"), Strategy);
        Capability->SetBoolField(TEXT("available"), bAvailable);
        Capability->SetStringField(TEXT("reason"), Reason);
        Capabilities.Add(MakeShared<FJsonValueObject>(Capability));
    };
    AddCapability(TEXT("data_layer"), bHasWorldPartition,
        bHasWorldPartition ? TEXT("The source world supports run-specific Data Layers.") : TEXT("The fixture does not use World Partition."));
    AddCapability(TEXT("candidate_level"), true, TEXT("A project-local candidate level is available as the safe fallback."));
    Twin->SetArrayField(TEXT("staging_capabilities"), Capabilities);

    FPassFile TwinArtifact{TEXT("scene_digital_twin"), TEXT("scene-digital-twin.json"), TEXT("application/json"), TEXT("utf-8-json"), FPaths::Combine(StagingRoot, TEXT("scene-digital-twin.json")), TEXT("")};
    if (!SaveJsonArtifact(Twin, TwinArtifact, OutError)) return false;

    TSharedPtr<FJsonObject> Plan = MakeShared<FJsonObject>();
    Plan->SetStringField(TEXT("schema_id"), TEXT("scene-change-plan/1"));
    Plan->SetStringField(TEXT("plan_id"), PlanId);
    Plan->SetStringField(TEXT("twin_id"), TwinId);
    Plan->SetStringField(TEXT("twin_sha256"), TwinArtifact.Sha256);
    Plan->SetStringField(TEXT("created_at"), CapturedAt);

    TSharedPtr<FJsonObject> Lighting = MakeShared<FJsonObject>();
    Lighting->SetStringField(TEXT("operation_id"), TEXT("lighting-main"));
    Lighting->SetStringField(TEXT("operation_type"), TEXT("set_lighting_rig"));
    Lighting->SetArrayField(TEXT("depends_on"), {});
    TSharedPtr<FJsonObject> LightFingerprints = MakeShared<FJsonObject>();
    LightFingerprints->SetStringField(LightEvidence->ActorId, LightEvidence->Fingerprint);
    Lighting->SetObjectField(TEXT("expected_source_fingerprints"), LightFingerprints);
    Lighting->SetObjectField(TEXT("write_scope"), WriteScopeJson(StageId, AssetRoot, LightEvidence->ActorId));
    Lighting->SetStringField(TEXT("idempotency_key"), PackageId + TEXT(":lighting-main"));
    Lighting->SetObjectField(TEXT("budget"), BudgetJson(1, 0, 30));
    Lighting->SetArrayField(TEXT("validators"), ValidatorValues({TEXT("protected_fingerprint"), TEXT("light_parameter_bounds"), TEXT("zero_source_mutations")}));
    Lighting->SetStringField(TEXT("cleanup"), TEXT("restore_staged_properties"));
    Lighting->SetArrayField(TEXT("target_light_ids"), {StringValue(LightEvidence->ActorId)});
    Lighting->SetNumberField(TEXT("intensity"), 5.5);
    Lighting->SetNumberField(TEXT("temperature_kelvin"), 4200.0);

    TSharedPtr<FJsonObject> PCG = MakeShared<FJsonObject>();
    PCG->SetStringField(TEXT("operation_id"), TEXT("pcg-scatter"));
    PCG->SetStringField(TEXT("operation_type"), TEXT("apply_pcg_layout"));
    PCG->SetArrayField(TEXT("depends_on"), {StringValue(TEXT("lighting-main"))});
    TSharedPtr<FJsonObject> PCGFingerprints = MakeShared<FJsonObject>();
    PCGFingerprints->SetStringField(PCGEvidence->ActorId, PCGEvidence->Fingerprint);
    PCG->SetObjectField(TEXT("expected_source_fingerprints"), PCGFingerprints);
    PCG->SetObjectField(TEXT("write_scope"), WriteScopeJson(StageId, AssetRoot, PCGEvidence->ActorId));
    PCG->SetStringField(TEXT("idempotency_key"), PackageId + TEXT(":pcg-scatter"));
    PCG->SetObjectField(TEXT("budget"), BudgetJson(1, 80, 60));
    PCG->SetArrayField(TEXT("validators"), ValidatorValues({TEXT("protected_fingerprint"), TEXT("pcg_graph_allowlist"), TEXT("bounds"), TEXT("no_collision"), TEXT("actor_budget"), TEXT("zero_source_mutations")}));
    PCG->SetStringField(TEXT("cleanup"), TEXT("delete_generated_actors"));
    PCG->SetStringField(TEXT("component_id"), PCGEvidence->PCGComponentId);
    PCG->SetStringField(TEXT("approved_graph_path"), PCGEvidence->PCGGraphPath);
    TSharedPtr<FJsonObject> GraphParameters = MakeShared<FJsonObject>();
    GraphParameters->SetNumberField(TEXT("density"), 0.35);
    GraphParameters->SetStringField(TEXT("asset_set"), TEXT("demo-rocks"));
    PCG->SetObjectField(TEXT("graph_parameters"), GraphParameters);
    PCG->SetNumberField(TEXT("seed"), 240827);
    Plan->SetArrayField(TEXT("operations"), {MakeShared<FJsonValueObject>(Lighting), MakeShared<FJsonValueObject>(PCG)});

    FPassFile PlanArtifact{TEXT("scene_change_plan"), TEXT("scene-change-plan.json"), TEXT("application/json"), TEXT("utf-8-json"), FPaths::Combine(StagingRoot, TEXT("scene-change-plan.json")), TEXT("")};
    if (!SaveJsonArtifact(Plan, PlanArtifact, OutError)) return false;

    SceneFingerprintParts.Sort();
    const FString SourceFingerprint = HashText(FString::Join(SceneFingerprintParts, TEXT("|")));
    TSharedPtr<FJsonObject> Receipt = MakeShared<FJsonObject>();
    Receipt->SetStringField(TEXT("schema_id"), TEXT("scene-dry-run-receipt/1"));
    Receipt->SetStringField(TEXT("receipt_id"), PackageId + TEXT("-dry"));
    Receipt->SetStringField(TEXT("twin_id"), TwinId);
    Receipt->SetStringField(TEXT("twin_sha256"), TwinArtifact.Sha256);
    Receipt->SetStringField(TEXT("plan_id"), PlanId);
    Receipt->SetStringField(TEXT("plan_sha256"), PlanArtifact.Sha256);
    Receipt->SetStringField(TEXT("source_scene_path"), World->GetOutermost()->GetName());
    Receipt->SetStringField(TEXT("source_scene_fingerprint_before"), SourceFingerprint);
    Receipt->SetStringField(TEXT("source_scene_fingerprint_after"), SourceFingerprint);
    Receipt->SetStringField(TEXT("staging_strategy"), bHasWorldPartition ? TEXT("data_layer") : TEXT("candidate_level"));
    Receipt->SetStringField(TEXT("stage_id"), StageId);
    TSharedPtr<FJsonObject> LightingSummary = MakeShared<FJsonObject>();
    LightingSummary->SetStringField(TEXT("operation_id"), TEXT("lighting-main"));
    LightingSummary->SetStringField(TEXT("operation_type"), TEXT("set_lighting_rig"));
    LightingSummary->SetArrayField(TEXT("target_ids"), {StringValue(LightEvidence->ActorId)});
    LightingSummary->SetArrayField(TEXT("parameter_names"), {StringValue(TEXT("intensity")), StringValue(TEXT("temperature_kelvin"))});
    TSharedPtr<FJsonObject> PCGSummary = MakeShared<FJsonObject>();
    PCGSummary->SetStringField(TEXT("operation_id"), TEXT("pcg-scatter"));
    PCGSummary->SetStringField(TEXT("operation_type"), TEXT("apply_pcg_layout"));
    PCGSummary->SetArrayField(TEXT("target_ids"), {StringValue(PCGEvidence->PCGComponentId)});
    PCGSummary->SetArrayField(TEXT("parameter_names"), {StringValue(TEXT("density")), StringValue(TEXT("asset_set")), StringValue(TEXT("seed"))});
    Receipt->SetArrayField(TEXT("planned_operations"), {MakeShared<FJsonValueObject>(LightingSummary), MakeShared<FJsonValueObject>(PCGSummary)});
    Receipt->SetObjectField(TEXT("protected_invariants"), ProtectedInvariants);
    Receipt->SetBoolField(TEXT("dry_run"), true);
    Receipt->SetNumberField(TEXT("committed_mutation_count"), 0);
    Receipt->SetStringField(TEXT("created_at"), CapturedAt);

    FPassFile ReceiptArtifact{TEXT("scene_dry_run_receipt"), TEXT("scene-dry-run-receipt.json"), TEXT("application/json"), TEXT("utf-8-json"), FPaths::Combine(StagingRoot, TEXT("scene-dry-run-receipt.json")), TEXT("")};
    if (!SaveJsonArtifact(Receipt, ReceiptArtifact, OutError)) return false;
    OutArtifacts = {TwinArtifact, PlanArtifact, ReceiptArtifact};
    return true;
}

bool WriteManifest(
    const FString& ManifestPath,
    const FString& PackageId,
    const FCaptureRequest& Request,
    const ACameraActor* Camera,
    const TArray<FPassFile>& Passes,
    const TArray<FPassFile>& SceneArtifacts,
    const TArray<AActor*>& ProtectedActors,
    const TArray<AActor*>& EditableActors,
    FString& OutError)
{
    const UCameraComponent* CameraComponent = Camera->GetCameraComponent();
    TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetStringField(TEXT("schema_id"), TEXT("scene-constraint-package/1"));
    Root->SetStringField(TEXT("package_id"), PackageId);

    TSharedPtr<FJsonObject> CameraJson = MakeShared<FJsonObject>();
    const bool bOrthographic = CameraComponent->ProjectionMode == ECameraProjectionMode::Orthographic;
    CameraJson->SetStringField(TEXT("projection"), bOrthographic ? TEXT("orthographic") : TEXT("perspective"));
    const FMatrix Matrix = Camera->GetActorTransform().ToMatrixWithScale();
    TArray<TSharedPtr<FJsonValue>> MatrixValues;
    for (int32 Row = 0; Row < 4; ++Row)
    {
        for (int32 Column = 0; Column < 4; ++Column)
        {
            MatrixValues.Add(MakeShared<FJsonValueNumber>(Matrix.M[Row][Column]));
        }
    }
    CameraJson->SetArrayField(TEXT("world_transform"), MatrixValues);
    if (bOrthographic)
    {
        CameraJson->SetNumberField(TEXT("ortho_width"), CameraComponent->OrthoWidth);
    }
    else
    {
        CameraJson->SetNumberField(TEXT("horizontal_fov_degrees"), CameraComponent->FieldOfView);
    }
    CameraJson->SetNumberField(TEXT("near_clip"), FMath::Max(0.001f, GNearClippingPlane));
    CameraJson->SetNumberField(TEXT("far_clip"), DefaultFarClip);
    CameraJson->SetNumberField(TEXT("width"), Request.Width);
    CameraJson->SetNumberField(TEXT("height"), Request.Height);
    Root->SetObjectField(TEXT("camera"), CameraJson);

    TArray<TSharedPtr<FJsonValue>> PassValues;
    for (const FPassFile& Pass : Passes)
    {
        TSharedPtr<FJsonObject> PassJson = MakeShared<FJsonObject>();
        PassJson->SetStringField(TEXT("kind"), Pass.Kind);
        PassJson->SetObjectField(TEXT("artifact"), ArtifactJson(Pass));
        PassJson->SetStringField(TEXT("encoding"), Pass.Encoding);
        PassValues.Add(MakeShared<FJsonValueObject>(PassJson));
    }
    Root->SetArrayField(TEXT("passes"), PassValues);
    for (const FPassFile& Artifact : SceneArtifacts)
    {
        Root->SetObjectField(Artifact.Kind, ArtifactJson(Artifact));
    }

    TArray<TSharedPtr<FJsonValue>> RegionValues;
    const auto AddRegion = [&RegionValues](const TCHAR* RegionId, const TCHAR* Mode, const TArray<AActor*>& Actors)
    {
        TSharedPtr<FJsonObject> Region = MakeShared<FJsonObject>();
        Region->SetStringField(TEXT("region_id"), RegionId);
        Region->SetStringField(TEXT("mode"), Mode);
        TArray<TSharedPtr<FJsonValue>> ObjectIds;
        for (const AActor* Actor : Actors)
        {
            ObjectIds.Add(StringValue(Actor->GetActorLabel()));
        }
        Region->SetArrayField(TEXT("object_ids"), ObjectIds);
        RegionValues.Add(MakeShared<FJsonValueObject>(Region));
    };
    AddRegion(TEXT("protected-selection"), TEXT("protected"), ProtectedActors);
    AddRegion(TEXT("editable-selection"), TEXT("editable"), EditableActors);
    Root->SetArrayField(TEXT("regions"), RegionValues);

    TSharedPtr<FJsonObject> Intent = MakeShared<FJsonObject>();
    Intent->SetStringField(TEXT("goal"), Request.Goal);
    Intent->SetArrayField(TEXT("preserve"), StringValues(Request.Preserve));
    Intent->SetArrayField(TEXT("prohibit"), StringValues(Request.Prohibit));
    Intent->SetArrayField(TEXT("reference_assets"), {});
    Root->SetObjectField(TEXT("art_intent"), Intent);

    TSharedPtr<FJsonObject> Provenance = MakeShared<FJsonObject>();
    Provenance->SetStringField(TEXT("application"), TEXT("Unreal Engine"));
    Provenance->SetStringField(TEXT("application_version"), FEngineVersion::Current().ToString());
    Provenance->SetStringField(TEXT("project_name"), FApp::GetProjectName());
    Provenance->SetStringField(TEXT("scene_name"), Camera->GetWorld()->GetOutermost()->GetName());
    Provenance->SetStringField(TEXT("captured_at"), FDateTime::UtcNow().ToIso8601());
    Root->SetObjectField(TEXT("provenance"), Provenance);

    TSharedPtr<FJsonObject> Delivery = MakeShared<FJsonObject>();
    Delivery->SetStringField(TEXT("color_space"), TEXT("sRGB"));
    Delivery->SetStringField(TEXT("file_format"), TEXT("png"));
    Delivery->SetStringField(TEXT("purpose"), TEXT("art_direction"));
    Root->SetObjectField(TEXT("delivery"), Delivery);

    FString JsonText;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&JsonText);
    if (!FJsonSerializer::Serialize(Root.ToSharedRef(), Writer) || !FFileHelper::SaveStringToFile(JsonText, *ManifestPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
    {
        OutError = TEXT("Could not publish the Scene Package manifest into staging.");
        return false;
    }
    return true;
}

bool WriteAtomicArchive(const FString& FinalPath, const FString& ManifestPath, const TArray<FPassFile>& Passes, const TArray<FPassFile>& SceneArtifacts, FString& OutError)
{
    const FString PartialPath = FinalPath + TEXT(".partial");
    if (!IsPathInside(FinalPath, GetExportRoot()) || !IsPathInside(PartialPath, GetExportRoot()))
    {
        OutError = TEXT("Scene Package destination escaped the project-owned export root.");
        return false;
    }
    IFileManager::Get().Delete(*PartialPath, false, true);
    IFileHandle* Handle = FPlatformFileManager::Get().GetPlatformFile().OpenWrite(*PartialPath, false, false);
    if (Handle == nullptr)
    {
        OutError = TEXT("Could not create the temporary Scene Package archive.");
        return false;
    }
    {
        FZipArchiveWriter Zip(Handle, EZipArchiveOptions::Deflate);
        TArray<uint8> Bytes;
        if (!FFileHelper::LoadFileToArray(Bytes, *ManifestPath))
        {
            OutError = TEXT("Could not read the staged Scene Package manifest.");
            return false;
        }
        Zip.AddFile(TEXT("scene-package.json"), Bytes, FDateTime::UtcNow());
        for (const FPassFile& Pass : Passes)
        {
            Bytes.Reset();
            if (!FFileHelper::LoadFileToArray(Bytes, *Pass.AbsolutePath) || Bytes.IsEmpty())
            {
                OutError = FString::Printf(TEXT("Could not read staged pass %s"), *Pass.Kind);
                return false;
            }
            Zip.AddFile(Pass.RelativePath, Bytes, FDateTime::UtcNow());
        }
        for (const FPassFile& Artifact : SceneArtifacts)
        {
            Bytes.Reset();
            if (!FFileHelper::LoadFileToArray(Bytes, *Artifact.AbsolutePath) || Bytes.IsEmpty())
            {
                OutError = FString::Printf(TEXT("Could not read staged artifact %s"), *Artifact.Kind);
                return false;
            }
            Zip.AddFile(Artifact.RelativePath, Bytes, FDateTime::UtcNow());
        }
    }
    if (IFileManager::Get().FileSize(*PartialPath) <= 0 || !IFileManager::Get().Move(*FinalPath, *PartialPath, true, true, false, true))
    {
        IFileManager::Get().Delete(*PartialPath, false, true);
        OutError = TEXT("Atomic Scene Package publication failed.");
        return false;
    }
    return true;
}

bool CollectSelection(ACameraActor*& OutCamera, TArray<AActor*>& OutProtected, TArray<AActor*>& OutEditable, FString& OutError)
{
    if (GEditor == nullptr || GEditor->GetSelectedActors() == nullptr)
    {
        OutError = TEXT("The editor actor selection is unavailable.");
        return false;
    }
    int32 CameraCount = 0;
    for (FSelectionIterator It(*GEditor->GetSelectedActors()); It; ++It)
    {
        AActor* Actor = Cast<AActor>(*It);
        if (ACameraActor* Camera = Cast<ACameraActor>(Actor))
        {
            OutCamera = Camera;
            ++CameraCount;
        }
        else if (Actor != nullptr && Actor->ActorHasTag(ProtectedTag))
        {
            OutProtected.Add(Actor);
        }
        else if (Actor != nullptr && Actor->ActorHasTag(EditableTag))
        {
            OutEditable.Add(Actor);
        }
    }
    if (CameraCount != 1)
    {
        OutError = TEXT("Select exactly one CameraActor.");
        return false;
    }
    if (OutProtected.IsEmpty() || OutEditable.IsEmpty())
    {
        OutError = TEXT("Select at least one ArtFlow.Protected actor and one ArtFlow.Editable actor.");
        return false;
    }
    return true;
}

bool ExportSelection(FString& OutArchivePath, FString& OutError)
{
    FString EmptyDigest;
    if (!HashBytes({}, EmptyDigest) || EmptyDigest != TEXT("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"))
    {
        OutError = TEXT("The built-in SHA-256 self-check failed; no package was published.");
        return false;
    }
    FCaptureRequest Request;
    if (!LoadCaptureRequest(Request, OutError))
    {
        return false;
    }
    ACameraActor* Camera = nullptr;
    TArray<AActor*> ProtectedActors;
    TArray<AActor*> EditableActors;
    if (!CollectSelection(Camera, ProtectedActors, EditableActors, OutError))
    {
        return false;
    }
    UWorld* World = Camera->GetWorld();
    if (World == nullptr || World->WorldType != EWorldType::Editor)
    {
        OutError = TEXT("Scene Package export requires an editor world.");
        return false;
    }

    IFileManager::Get().MakeDirectory(*GetExportRoot(), true);
    const FString PackageId = TEXT("artflow-ue-") + FGuid::NewGuid().ToString(EGuidFormats::Digits).ToLower();
    const FString StagingRoot = FPaths::Combine(GetBridgeRoot(), TEXT("Staging"), PackageId);
    if (!IsPathInside(StagingRoot, FPaths::Combine(GetBridgeRoot(), TEXT("Staging"))))
    {
        OutError = TEXT("Scene Package staging path escaped its project-owned root.");
        return false;
    }
    IFileManager::Get().MakeDirectory(*FPaths::Combine(StagingRoot, TEXT("passes")), true);
    ON_SCOPE_EXIT
    {
        IFileManager::Get().DeleteDirectory(*StagingRoot, false, true);
    };

    TArray<FPassFile> Passes = {
        {TEXT("beauty"), TEXT("passes/beauty.png"), TEXT("image/png"), TEXT("srgb8"), FPaths::Combine(StagingRoot, TEXT("passes/beauty.png")), TEXT("")},
        {TEXT("depth"), TEXT("passes/depth.exr"), TEXT("image/x-exr"), TEXT("linear-distance-centimeters"), FPaths::Combine(StagingRoot, TEXT("passes/depth.exr")), TEXT("")},
        {TEXT("world_normal"), TEXT("passes/world-normal.exr"), TEXT("image/x-exr"), TEXT("unreal-world-normal-rgb"), FPaths::Combine(StagingRoot, TEXT("passes/world-normal.exr")), TEXT("")},
        {TEXT("object_id"), TEXT("passes/object-id.png"), TEXT("image/png"), TEXT("custom-stencil-u8"), FPaths::Combine(StagingRoot, TEXT("passes/object-id.png")), TEXT("")}
    };

    FScopedSlowTask Progress(6.0f, LOCTEXT("CaptureProgress", "Exporting ArtFlow Scene Package"));
    Progress.MakeDialog(true);
    const auto Step = [&Progress, &OutError](const FText& Message) -> bool
    {
        Progress.EnterProgressFrame(1.0f, Message);
        if (Progress.ShouldCancel())
        {
            OutError = TEXT("Scene Package export was cancelled; no package was published.");
            return false;
        }
        return true;
    };

    if (!Step(LOCTEXT("BeautyPass", "Capturing beauty")) ||
        !CapturePass(World, Camera, Request, SCS_FinalColorLDR, false, Passes[0].AbsolutePath, nullptr, {}, OutError))
    {
        return false;
    }
    if (!Step(LOCTEXT("DepthPass", "Capturing linear depth")) ||
        !CapturePass(World, Camera, Request, SCS_SceneDepth, true, Passes[1].AbsolutePath, nullptr, {}, OutError))
    {
        return false;
    }
    if (!Step(LOCTEXT("NormalPass", "Capturing world normals")) ||
        !CapturePass(World, Camera, Request, SCS_Normal, true, Passes[2].AbsolutePath, nullptr, {}, OutError))
    {
        return false;
    }

    TArray<FPrimitiveStencilState> PreviousStencilStates;
    TArray<AActor*> ObjectActors = ProtectedActors;
    ObjectActors.Append(EditableActors);
    int32 StencilId = 1;
    for (AActor* Actor : ObjectActors)
    {
        TInlineComponentArray<UPrimitiveComponent*> Components(Actor);
        for (UPrimitiveComponent* Component : Components)
        {
            PreviousStencilStates.Add({Component, Component->bRenderCustomDepth != 0, Component->CustomDepthStencilValue});
            Component->SetRenderCustomDepth(true);
            Component->SetCustomDepthStencilValue(StencilId);
        }
        StencilId = FMath::Min(255, StencilId + 1);
    }
    ON_SCOPE_EXIT
    {
        for (const FPrimitiveStencilState& State : PreviousStencilStates)
        {
            if (UPrimitiveComponent* Component = State.Component.Get())
            {
                Component->SetRenderCustomDepth(State.bRenderCustomDepth);
                Component->SetCustomDepthStencilValue(State.StencilValue);
            }
        }
    };

    FBufferVisualizationData& VisualizationData = GetBufferVisualizationData();
    if (!VisualizationData.IsInitialized())
    {
        OutError = TEXT("The renderer buffer-visualization registry is not initialized.");
        return false;
    }
    UMaterialInterface* CustomStencil = VisualizationData.GetMaterial(TEXT("CustomStencil"));
    if (CustomStencil == nullptr)
    {
        OutError = TEXT("The renderer does not expose the CustomStencil visualization pass.");
        return false;
    }
    if (!Step(LOCTEXT("ObjectIdPass", "Capturing object IDs")) ||
        !CapturePass(World, Camera, Request, SCS_FinalColorLDR, false, Passes[3].AbsolutePath, CustomStencil, ObjectActors, OutError))
    {
        return false;
    }

    for (FPassFile& Pass : Passes)
    {
        if (!HashFile(Pass.AbsolutePath, Pass.Sha256, OutError))
        {
            return false;
        }
    }
    TArray<FPassFile> SceneArtifacts;
    if (!WriteSceneDeltaArtifacts(World, StagingRoot, PackageId, SceneArtifacts, OutError))
    {
        return false;
    }
    if (!Step(LOCTEXT("ManifestPass", "Writing signed manifest")))
    {
        return false;
    }
    const FString ManifestPath = FPaths::Combine(StagingRoot, TEXT("scene-package.json"));
    if (!WriteManifest(ManifestPath, PackageId, Request, Camera, Passes, SceneArtifacts, ProtectedActors, EditableActors, OutError))
    {
        return false;
    }
    if (!Step(LOCTEXT("ArchivePass", "Publishing atomic package")))
    {
        return false;
    }
    OutArchivePath = FPaths::Combine(GetExportRoot(), PackageId + TEXT(".zip"));
    return WriteAtomicArchive(OutArchivePath, ManifestPath, Passes, SceneArtifacts, OutError);
}

UPCGGraph* LoadOrCreateDemoPCGGraph(FString& OutError)
{
    const FString AssetPath = TEXT("/Game/ArtFlow/PCG/PCG_ArtFlowScatter.PCG_ArtFlowScatter");
    const FString PackageName = TEXT("/Game/ArtFlow/PCG/PCG_ArtFlowScatter");
    UPackage* Package = nullptr;
    UPCGGraph* Graph = LoadObject<UPCGGraph>(nullptr, *AssetPath);
    const bool bGraphAlreadyAuthored = Graph != nullptr && Graph->GetNodes().Num() >= 2;
    if (Graph != nullptr)
    {
        Package = Graph->GetOutermost();
        Graph->Modify();
    }
    else
    {
        Package = CreatePackage(*PackageName);
        Graph = NewObject<UPCGGraph>(Package, TEXT("PCG_ArtFlowScatter"), RF_Public | RF_Standalone);
    }
    if (Graph == nullptr)
    {
        OutError = TEXT("Could not create the project-owned ArtFlow PCG graph.");
        return nullptr;
    }
    if (!Graph->GetUserParametersStruct()->FindPropertyDescByName(TEXT("density")))
    {
        Graph->AddUserParameters({
            FPropertyBagPropertyDesc(TEXT("density"), EPropertyBagPropertyType::Float),
            FPropertyBagPropertyDesc(TEXT("asset_set"), EPropertyBagPropertyType::String)});
        Graph->SetGraphParameter<float>(TEXT("density"), 0.35f);
        Graph->SetGraphParameter<FString>(TEXT("asset_set"), TEXT("demo-rocks"));
    }

    const FString PropAssetPath = TEXT("/Game/ArtFlow/Props/SM_ArtFlowRock.SM_ArtFlowRock");
    UStaticMesh* PropMesh = LoadObject<UStaticMesh>(nullptr, *PropAssetPath);
    if (PropMesh == nullptr)
    {
        UStaticMesh* SourceMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cone.Cone"));
        IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get();
        PropMesh = Cast<UStaticMesh>(AssetTools.DuplicateAsset(TEXT("SM_ArtFlowRock"), TEXT("/Game/ArtFlow/Props"), SourceMesh));
        if (PropMesh != nullptr)
        {
            UPackage* PropPackage = PropMesh->GetOutermost();
            const FString PropFilename = FPackageName::LongPackageNameToFilename(TEXT("/Game/ArtFlow/Props/SM_ArtFlowRock"), FPackageName::GetAssetPackageExtension());
            IFileManager::Get().MakeDirectory(*FPaths::GetPath(PropFilename), true);
            FSavePackageArgs PropSaveArgs;
            PropSaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
            PropSaveArgs.SaveFlags = SAVE_NoError;
            if (!UPackage::SavePackage(PropPackage, PropMesh, *PropFilename, PropSaveArgs))
            {
                OutError = TEXT("Could not save the project-owned ArtFlow primitive prop.");
                return nullptr;
            }
        }
    }
    if (PropMesh == nullptr)
    {
        OutError = TEXT("Could not create the project-owned ArtFlow primitive prop.");
        return nullptr;
    }
    if (bGraphAlreadyAuthored)
    {
        return Graph;
    }

    UPCGCreatePointsSettings* PointSettings = nullptr;
    UPCGNode* PointNode = Graph->AddNodeOfType<UPCGCreatePointsSettings>(PointSettings);
    UPCGStaticMeshSpawnerSettings* SpawnerSettings = nullptr;
    UPCGNode* SpawnerNode = Graph->AddNodeOfType<UPCGStaticMeshSpawnerSettings>(SpawnerSettings);
    if (PointNode == nullptr || PointSettings == nullptr || SpawnerNode == nullptr || SpawnerSettings == nullptr)
    {
        OutError = TEXT("Could not author the reviewed Create Points to Static Mesh Spawner graph.");
        return nullptr;
    }
    PointSettings->CoordinateSpace = EPCGCoordinateSpace::World;
    PointSettings->PointsToCreate.Reset();
    const TArray<FVector> Positions = {
        FVector(-40, -330, 20), FVector(80, -270, 26), FVector(190, -205, 18),
        FVector(260, -90, 32), FVector(300, 45, 20), FVector(250, 175, 28),
        FVector(155, 300, 22), FVector(25, 345, 30), FVector(-95, 285, 18),
        FVector(-170, 175, 26), FVector(-200, 45, 20), FVector(-150, -120, 30)};
    for (int32 Index = 0; Index < Positions.Num(); ++Index)
    {
        FPCGPoint& Point = PointSettings->PointsToCreate.AddDefaulted_GetRef();
        const float UniformScale = 0.45f + static_cast<float>((Index * 7) % 5) * 0.07f;
        Point.Transform = FTransform(FRotator(0, Index * 29.0f, 0), Positions[Index], FVector(UniformScale));
        Point.Seed = 240827 + Index;
        Point.Density = 1.0f;
    }
    SpawnerSettings->SetMeshSelectorType(UPCGMeshSelectorWeighted::StaticClass());
    UPCGMeshSelectorWeighted* Selector = Cast<UPCGMeshSelectorWeighted>(SpawnerSettings->MeshSelectorParameters);
    if (Selector == nullptr)
    {
        OutError = TEXT("Could not configure the reviewed ArtFlow PCG mesh selector.");
        return nullptr;
    }
    Selector->MeshEntries.Reset();
    FPCGMeshSelectorWeightedEntry Entry(TSoftObjectPtr<UStaticMesh>(PropMesh), 1);
    Entry.Descriptor.ComponentTags = {TEXT("ArtFlow.Generated"), TEXT("ArtFlow.PCG.ArtFlowScatter")};
    Selector->MeshEntries.Add(Entry);
    SpawnerSettings->bSynchronousLoad = true;
    Graph->AddLabeledEdge(PointNode, PCGPinConstants::DefaultOutputLabel, SpawnerNode, PCGPinConstants::DefaultInputLabel);
    Graph->AddLabeledEdge(SpawnerNode, PCGPinConstants::DefaultOutputLabel, Graph->GetOutputNode(), PCGPinConstants::DefaultOutputLabel);
    if (!Graph->GetOuter()->HasAnyFlags(RF_WasLoaded))
    {
        FAssetRegistryModule::AssetCreated(Graph);
    }
    Package->MarkPackageDirty();
    const FString Filename = FPackageName::LongPackageNameToFilename(PackageName, FPackageName::GetAssetPackageExtension());
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Filename), true);
    FSavePackageArgs SaveArgs;
    SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
    SaveArgs.SaveFlags = SAVE_NoError;
    if (!UPackage::SavePackage(Package, Graph, *Filename, SaveArgs))
    {
        OutError = TEXT("Could not save the project-owned ArtFlow PCG graph.");
        return nullptr;
    }
    return Graph;
}

int32 CountGeneratedInstances(UWorld* World)
{
    int32 Count = 0;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        TInlineComponentArray<UInstancedStaticMeshComponent*> Components(*It);
        for (const UInstancedStaticMeshComponent* Component : Components)
        {
            if (Component->ComponentHasTag(TEXT("ArtFlow.Generated")))
            {
                Count += Component->GetInstanceCount();
            }
        }
    }
    return Count;
}

AActor* FindActorByLabel(UWorld* World, const FString& Label)
{
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (It->GetActorLabel() == Label)
        {
            return *It;
        }
    }
    return nullptr;
}

FString ActorFingerprint(AActor* Actor)
{
    FSceneActorEvidence Evidence;
    BuildActorFact(Actor, Evidence);
    return Evidence.Fingerprint;
}

FString ProtectedSemanticFingerprint(AActor* Actor)
{
    FString Stable = Actor->GetClass()->GetPathName() + TEXT("|") + Actor->GetActorLabel() + TEXT("|") +
        Actor->GetActorTransform().ToHumanReadableString();
    TArray<FString> Tags;
    for (const FName Tag : Actor->Tags) Tags.Add(Tag.ToString());
    Tags.Sort();
    Stable += TEXT("|") + FString::Join(Tags, TEXT(","));
    TInlineComponentArray<UStaticMeshComponent*> MeshComponents(Actor);
    for (const UStaticMeshComponent* MeshComponent : MeshComponents)
    {
        Stable += TEXT("|") + (MeshComponent->GetStaticMesh() == nullptr ? TEXT("none") : MeshComponent->GetStaticMesh()->GetPathName());
        for (int32 Index = 0; Index < MeshComponent->GetNumMaterials(); ++Index)
        {
            const UMaterialInterface* Material = MeshComponent->GetMaterial(Index);
            Stable += TEXT("|") + (Material == nullptr ? TEXT("none") : Material->GetPathName());
        }
    }
    return HashText(Stable);
}

bool StartCandidateExecution(UPCGComponent*& OutPCG, bool& OutReconciled, FString& OutSourceHash, FString& OutProtectedHash, FString& OutError)
{
    UWorld* SourceWorld = GEditor == nullptr ? nullptr : GEditor->GetEditorWorldContext().World();
    if (SourceWorld == nullptr || SourceWorld->GetOutermost()->GetName() != TEXT("/Game/ArtFlowDemo"))
    {
        OutError = TEXT("Candidate execution requires the frozen /Game/ArtFlowDemo source map.");
        return false;
    }
    const FString SourceFilename = FPackageName::LongPackageNameToFilename(TEXT("/Game/ArtFlowDemo"), FPackageName::GetMapPackageExtension());
    if (!HashFile(SourceFilename, OutSourceHash, OutError))
    {
        return false;
    }
    AActor* SourceProtected = FindActorByLabel(SourceWorld, TEXT("Protected_Blockout"));
    if (SourceProtected == nullptr || ActorFingerprint(SourceProtected) != TEXT("c840399a559a02edb48974263f78e2f30ed4c4a1ad262cb0db7afeae494f1910"))
    {
        OutError = TEXT("Frozen protected actor fingerprint no longer matches the M7-S1 plan.");
        return false;
    }
    OutProtectedHash = ProtectedSemanticFingerprint(SourceProtected);

    UPCGGraph* ReviewedGraph = LoadOrCreateDemoPCGGraph(OutError);
    if (ReviewedGraph == nullptr)
    {
        return false;
    }
    UWorld* CandidateWorld = nullptr;
    const FString CandidateFilename = FPackageName::LongPackageNameToFilename(CandidatePackage, FPackageName::GetMapPackageExtension());
    if (!IFileManager::Get().FileExists(*CandidateFilename))
    {
        IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get();
        CandidateWorld = Cast<UWorld>(AssetTools.DuplicateAsset(
            FPackageName::GetLongPackageAssetName(CandidatePackage),
            FPackageName::GetLongPackagePath(CandidatePackage), SourceWorld));
        if (CandidateWorld == nullptr)
        {
            OutError = TEXT("Could not create the content-addressed candidate level.");
            return false;
        }
        UPackage* CandidatePackageObject = CandidateWorld->GetOutermost();
        FSavePackageArgs CandidateSaveArgs;
        CandidateSaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
        CandidateSaveArgs.SaveFlags = SAVE_NoError;
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(CandidateFilename), true);
        if (!UPackage::SavePackage(CandidatePackageObject, CandidateWorld, *CandidateFilename, CandidateSaveArgs))
        {
            OutError = TEXT("Could not persist the content-addressed candidate level.");
            return false;
        }
        CandidateWorld = nullptr;
        FText UnloadError;
        if (!UPackageTools::UnloadPackages({CandidatePackageObject}, UnloadError, true))
        {
            OutError = FString::Printf(TEXT("Could not release duplicated candidate package before loading it: %s"), *UnloadError.ToString());
            return false;
        }
    }
    if (!FEditorFileUtils::LoadMap(CandidateFilename, false, false))
    {
        OutError = TEXT("Could not load the content-addressed candidate level.");
        return false;
    }
    CandidateWorld = GEditor->GetEditorWorldContext().World();
    AActor* LightActor = FindActorByLabel(CandidateWorld, TEXT("ArtFlow_KeyLight"));
    AActor* Editable = FindActorByLabel(CandidateWorld, TEXT("Editable_Form"));
    AActor* Protected = FindActorByLabel(CandidateWorld, TEXT("Protected_Blockout"));
    if (LightActor == nullptr || Editable == nullptr || Protected == nullptr)
    {
        OutError = TEXT("Candidate level is missing a frozen operation target or protected actor.");
        return false;
    }
    ULightComponent* Light = LightActor->FindComponentByClass<ULightComponent>();
    OutPCG = Editable->FindComponentByClass<UPCGComponent>();
    if (Light == nullptr || OutPCG == nullptr)
    {
        OutError = TEXT("Candidate targets do not expose the required typed components.");
        return false;
    }
    OutPCG->SetGraph(ReviewedGraph);
    OutPCG->Seed = 240827;
    Light->SetIntensity(5.5f);
    Light->SetUseTemperature(true);
    Light->SetTemperature(4200.0f);
    const int32 ExistingInstances = CountGeneratedInstances(CandidateWorld);
    OutReconciled = ExistingInstances == 12;
    if (!OutReconciled)
    {
        OutPCG->CleanupLocalImmediate(true, true);
        OutPCG->GenerateLocal(true);
    }
    return true;
}

bool FinalizeCandidateExecution(bool bReconciled, const FString& SourceHash, const FString& ProtectedHash, FString& OutReceiptPath, FString& OutError)
{
    UWorld* World = GEditor == nullptr ? nullptr : GEditor->GetEditorWorldContext().World();
    if (World == nullptr || World->GetOutermost()->GetName() != CandidatePackage)
    {
        OutError = TEXT("The candidate world was replaced before execution could be finalized.");
        return false;
    }
    const int32 InstanceCount = CountGeneratedInstances(World);
    if (InstanceCount != 12)
    {
        OutError = FString::Printf(TEXT("Reviewed PCG graph produced %d instances; expected exactly 12."), InstanceCount);
        return false;
    }
    AActor* Camera = FindActorByLabel(World, TEXT("ArtFlow_Camera"));
    AActor* Protected = FindActorByLabel(World, TEXT("Protected_Blockout"));
    if (Camera == nullptr || Protected == nullptr)
    {
        OutError = TEXT("Candidate render camera or protected actor is missing.");
        return false;
    }
    const FString ProtectedAfter = ProtectedSemanticFingerprint(Protected);
    if (ProtectedAfter != ProtectedHash)
    {
        OutError = TEXT("Candidate execution changed the protected actor fingerprint.");
        return false;
    }
    const FString OutputRoot = FPaths::Combine(GetBridgeRoot(), TEXT("Candidates"), FrozenStageId);
    IFileManager::Get().MakeDirectory(*OutputRoot, true);
    const FString BeautyPath = FPaths::Combine(OutputRoot, TEXT("candidate-beauty.png"));
    // A freshly imported/generated material can still be compiling when the staged
    // candidate is reopened. Capturing before compilation completes produces UE's
    // fallback checker material and is not valid visual evidence.
    FAssetCompilingManager::Get().FinishAllCompilation();
    FlushRenderingCommands();
    FCaptureRequest Request;
    if (!LoadCaptureRequest(Request, OutError) ||
        !CapturePass(World, Cast<ACameraActor>(Camera), Request, SCS_FinalColorLDR, false, BeautyPath, nullptr, {}, OutError))
    {
        return false;
    }
    FString BeautyHash;
    if (!HashFile(BeautyPath, BeautyHash, OutError))
    {
        return false;
    }
    const FString CandidateFilename = FPackageName::LongPackageNameToFilename(CandidatePackage, FPackageName::GetMapPackageExtension());
    if (!FEditorFileUtils::SaveLevel(World->PersistentLevel, CandidateFilename))
    {
        OutError = TEXT("Could not save the staged candidate level.");
        return false;
    }
    FString SourceAfter;
    const FString SourceFilename = FPackageName::LongPackageNameToFilename(TEXT("/Game/ArtFlowDemo"), FPackageName::GetMapPackageExtension());
    if (!HashFile(SourceFilename, SourceAfter, OutError) || SourceAfter != SourceHash)
    {
        OutError = TEXT("Source level package changed during candidate execution.");
        return false;
    }

    TSharedPtr<FJsonObject> Receipt = MakeShared<FJsonObject>();
    Receipt->SetStringField(TEXT("schema_id"), TEXT("scene-execution-receipt/1"));
    Receipt->SetStringField(TEXT("receipt_id"), FrozenStageId + (bReconciled ? TEXT("-reconcile") : TEXT("-execute")));
    Receipt->SetStringField(TEXT("twin_id"), FrozenTwinId);
    Receipt->SetStringField(TEXT("twin_sha256"), FrozenTwinSha);
    Receipt->SetStringField(TEXT("plan_id"), FrozenPlanId);
    Receipt->SetStringField(TEXT("plan_sha256"), FrozenPlanSha);
    Receipt->SetStringField(TEXT("source_scene_path"), TEXT("/Game/ArtFlowDemo"));
    Receipt->SetStringField(TEXT("source_scene_fingerprint_before"), SourceHash);
    Receipt->SetStringField(TEXT("source_scene_fingerprint_after"), SourceAfter);
    Receipt->SetStringField(TEXT("candidate_scene_path"), CandidatePackage);
    Receipt->SetStringField(TEXT("stage_id"), FrozenStageId);
    Receipt->SetStringField(TEXT("status"), TEXT("staged"));
    Receipt->SetNumberField(TEXT("execution_attempt"), bReconciled ? 2 : 1);
    Receipt->SetBoolField(TEXT("reconciled"), bReconciled);

    const FString OperationStatus = bReconciled ? TEXT("reconciled") : TEXT("executed");
    TSharedPtr<FJsonObject> IntensityChange = MakeShared<FJsonObject>();
    IntensityChange->SetStringField(TEXT("property_name"), TEXT("intensity"));
    IntensityChange->SetNumberField(TEXT("before"), 8.0);
    IntensityChange->SetNumberField(TEXT("after"), 5.5);
    TSharedPtr<FJsonObject> TemperatureChange = MakeShared<FJsonObject>();
    TemperatureChange->SetStringField(TEXT("property_name"), TEXT("temperature_kelvin"));
    TemperatureChange->SetNumberField(TEXT("before"), 6500.0);
    TemperatureChange->SetNumberField(TEXT("after"), 4200.0);
    TSharedPtr<FJsonObject> Lighting = MakeShared<FJsonObject>();
    Lighting->SetStringField(TEXT("operation_id"), TEXT("lighting-main"));
    Lighting->SetStringField(TEXT("operation_type"), TEXT("set_lighting_rig"));
    Lighting->SetStringField(TEXT("idempotency_key"), FrozenPlanId.Replace(TEXT("-plan"), TEXT(":")) + TEXT("lighting-main"));
    Lighting->SetStringField(TEXT("status"), OperationStatus);
    Lighting->SetArrayField(TEXT("target_ids"), StringValues({TEXT("2fd6e5d1474ecd751f1b8f8729e64ad1")}));
    Lighting->SetArrayField(TEXT("property_changes"), {MakeShared<FJsonValueObject>(IntensityChange), MakeShared<FJsonValueObject>(TemperatureChange)});
    Lighting->SetNumberField(TEXT("generated_instance_count"), 0);
    Lighting->SetArrayField(TEXT("generated_resource_paths"), {});
    TSharedPtr<FJsonObject> PCG = MakeShared<FJsonObject>();
    PCG->SetStringField(TEXT("operation_id"), TEXT("pcg-scatter"));
    PCG->SetStringField(TEXT("operation_type"), TEXT("apply_pcg_layout"));
    PCG->SetStringField(TEXT("idempotency_key"), FrozenPlanId.Replace(TEXT("-plan"), TEXT(":")) + TEXT("pcg-scatter"));
    PCG->SetStringField(TEXT("status"), OperationStatus);
    PCG->SetArrayField(TEXT("target_ids"), StringValues({TEXT("3fa0497b43ee5f7a52b02f9ebd35573b:pcg_artflowscatter")}));
    PCG->SetArrayField(TEXT("property_changes"), {});
    PCG->SetNumberField(TEXT("generated_instance_count"), InstanceCount);
    PCG->SetArrayField(TEXT("generated_resource_paths"), StringValues({TEXT("/Game/ArtFlow/Props/SM_ArtFlowRock"), TEXT("/Game/ArtFlow/PCG/PCG_ArtFlowScatter")}));
    Receipt->SetArrayField(TEXT("operations"), {MakeShared<FJsonValueObject>(Lighting), MakeShared<FJsonValueObject>(PCG)});
    TSharedPtr<FJsonObject> ProtectedBefore = MakeShared<FJsonObject>();
    ProtectedBefore->SetStringField(TEXT("5e5124c6414eac2826f9e9a1eba6c9d9"), ProtectedHash);
    Receipt->SetObjectField(TEXT("protected_invariants_before"), ProtectedBefore);
    Receipt->SetObjectField(TEXT("protected_invariants_after"), ProtectedBefore);
    Receipt->SetStringField(TEXT("candidate_beauty_path"), BeautyPath);
    Receipt->SetStringField(TEXT("candidate_beauty_sha256"), BeautyHash);
    Receipt->SetStringField(TEXT("created_at"), FDateTime::UtcNow().ToIso8601());
    FString Text;
    FJsonSerializer::Serialize(Receipt.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    OutReceiptPath = FPaths::Combine(OutputRoot, bReconciled ? TEXT("scene-execution-reconcile-receipt.json") : TEXT("scene-execution-receipt.json"));
    return FFileHelper::SaveStringToFile(Text, *OutReceiptPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

bool ExecuteStageDisposition(bool bPublish, FString& OutReceiptPath, FString& OutError)
{
    const FString SourceFilename = FPackageName::LongPackageNameToFilename(TEXT("/Game/ArtFlowDemo"), FPackageName::GetMapPackageExtension());
    FString SourceBefore;
    if (!HashFile(SourceFilename, SourceBefore, OutError)) return false;
    const FString CandidateFilename = FPackageName::LongPackageNameToFilename(CandidatePackage, FPackageName::GetMapPackageExtension());
    if (!IFileManager::Get().FileExists(*CandidateFilename))
    {
        OutError = TEXT("The content-addressed candidate level does not exist.");
        return false;
    }
    TArray<FString> AffectedPaths;
    if (bPublish)
    {
        const FString PublishedPackage = TEXT("/Game/ArtFlow/Published/AF_cb2176a7a45bbad1");
        const FString PublishedFilename = FPackageName::LongPackageNameToFilename(PublishedPackage, FPackageName::GetMapPackageExtension());
        if (!IFileManager::Get().FileExists(*PublishedFilename))
        {
            const FString CandidateObjectPath = CandidatePackage + TEXT(".") + FPackageName::GetLongPackageAssetName(CandidatePackage);
            UWorld* CandidateWorld = LoadObject<UWorld>(nullptr, *CandidateObjectPath);
            if (CandidateWorld == nullptr)
            {
                OutError = TEXT("Could not load the staged candidate for publication.");
                return false;
            }
            IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get();
            UWorld* PublishedWorld = Cast<UWorld>(AssetTools.DuplicateAsset(
                FPackageName::GetLongPackageAssetName(PublishedPackage),
                FPackageName::GetLongPackagePath(PublishedPackage), CandidateWorld));
            if (PublishedWorld == nullptr)
            {
                OutError = TEXT("Could not duplicate the staged candidate into the published namespace.");
                return false;
            }
            FSavePackageArgs SaveArgs;
            SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
            SaveArgs.SaveFlags = SAVE_NoError;
            IFileManager::Get().MakeDirectory(*FPaths::GetPath(PublishedFilename), true);
            if (!UPackage::SavePackage(PublishedWorld->GetOutermost(), PublishedWorld, *PublishedFilename, SaveArgs))
            {
                OutError = TEXT("Could not save the published candidate level.");
                return false;
            }
        }
        AffectedPaths.Add(PublishedPackage);
    }
    else
    {
        if (!IFileManager::Get().Delete(*CandidateFilename, false, true, true))
        {
            OutError = TEXT("Could not remove the exact content-addressed candidate level.");
            return false;
        }
        AffectedPaths.Add(CandidatePackage);
    }
    FString SourceAfter;
    if (!HashFile(SourceFilename, SourceAfter, OutError) || SourceAfter != SourceBefore)
    {
        OutError = TEXT("Disposition changed the source scene package.");
        return false;
    }
    TSharedPtr<FJsonObject> Receipt = MakeShared<FJsonObject>();
    Receipt->SetStringField(TEXT("schema_id"), TEXT("scene-disposition-receipt/1"));
    Receipt->SetStringField(TEXT("receipt_id"), FrozenStageId + (bPublish ? TEXT("-published") : TEXT("-discarded")));
    Receipt->SetStringField(TEXT("execution_receipt_id"), FrozenStageId + TEXT("-execute"));
    Receipt->SetStringField(TEXT("plan_sha256"), FrozenPlanSha);
    Receipt->SetStringField(TEXT("stage_id"), FrozenStageId);
    Receipt->SetStringField(TEXT("candidate_scene_path"), CandidatePackage);
    Receipt->SetStringField(TEXT("disposition"), bPublish ? TEXT("published") : TEXT("discarded"));
    Receipt->SetBoolField(TEXT("source_overwritten"), false);
    Receipt->SetArrayField(TEXT("affected_paths"), StringValues(AffectedPaths));
    Receipt->SetStringField(TEXT("created_at"), FDateTime::UtcNow().ToIso8601());
    FString Text;
    FJsonSerializer::Serialize(Receipt.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    const FString OutputRoot = FPaths::Combine(GetBridgeRoot(), TEXT("Candidates"), FrozenStageId);
    IFileManager::Get().MakeDirectory(*OutputRoot, true);
    OutReceiptPath = FPaths::Combine(OutputRoot, bPublish ? TEXT("scene-publish-receipt.json") : TEXT("scene-discard-receipt.json"));
    return FFileHelper::SaveStringToFile(Text, *OutReceiptPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

bool CreateAutomationScene(FString& OutError)
{
    if (GEditor == nullptr)
    {
        OutError = TEXT("GEditor is unavailable.");
        return false;
    }
    UWorld* World = GEditor->GetEditorWorldContext().World();
    if (World == nullptr)
    {
        OutError = TEXT("Editor world is not ready.");
        return false;
    }

    UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    UStaticMesh* Sphere = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    if (Cube == nullptr || Sphere == nullptr)
    {
        OutError = TEXT("Built-in demo meshes are unavailable.");
        return false;
    }

    ACameraActor* Camera = World->SpawnActor<ACameraActor>(FVector(-900.0, 0.0, 420.0), FRotator(-18.0, 0.0, 0.0));
    AStaticMeshActor* Protected = World->SpawnActor<AStaticMeshActor>(FVector(0.0, -150.0, 100.0), FRotator::ZeroRotator);
    AStaticMeshActor* Editable = World->SpawnActor<AStaticMeshActor>(FVector(0.0, 170.0, 110.0), FRotator::ZeroRotator);
    AStaticMeshActor* Ground = World->SpawnActor<AStaticMeshActor>(FVector(100.0, 0.0, -55.0), FRotator::ZeroRotator);
    ADirectionalLight* Light = World->SpawnActor<ADirectionalLight>(FVector::ZeroVector, FRotator(-35.0, -25.0, 0.0));
    if (Camera == nullptr || Protected == nullptr || Editable == nullptr || Ground == nullptr || Light == nullptr)
    {
        OutError = TEXT("Could not create the fixed ArtFlow validation scene.");
        return false;
    }
    Camera->SetActorLabel(TEXT("ArtFlow_Camera"));
    Camera->GetCameraComponent()->FieldOfView = 55.0f;
    Protected->SetActorLabel(TEXT("Protected_Blockout"));
    Protected->Tags.Add(ProtectedTag);
    Protected->GetStaticMeshComponent()->SetStaticMesh(Cube);
    Protected->SetActorScale3D(FVector(2.2, 2.2, 2.2));
    Editable->SetActorLabel(TEXT("Editable_Form"));
    Editable->Tags.Add(EditableTag);
    Editable->GetStaticMeshComponent()->SetStaticMesh(Sphere);
    Editable->SetActorScale3D(FVector(1.5, 1.5, 1.5));
    Ground->SetActorLabel(TEXT("ArtFlow_Ground"));
    Ground->GetStaticMeshComponent()->SetStaticMesh(Cube);
    Ground->SetActorScale3D(FVector(8.0, 8.0, 0.5));
    Light->SetActorLabel(TEXT("ArtFlow_KeyLight"));
    Light->GetLightComponent()->SetIntensity(8.0f);
    UPCGGraph* PCGGraph = LoadOrCreateDemoPCGGraph(OutError);
    if (PCGGraph == nullptr)
    {
        return false;
    }
    UPCGComponent* PCGComponent = NewObject<UPCGComponent>(Editable, TEXT("PCG_ArtFlowScatter"));
    if (PCGComponent == nullptr)
    {
        OutError = TEXT("Could not create the ArtFlow PCG component.");
        return false;
    }
    Editable->AddInstanceComponent(PCGComponent);
    PCGComponent->SetGraph(PCGGraph);
    PCGComponent->Seed = 240827;
    PCGComponent->GenerationTrigger = EPCGComponentGenerationTrigger::GenerateOnDemand;
    PCGComponent->RegisterComponent();

    GEditor->SelectNone(false, true, false);
    GEditor->SelectActor(Camera, true, false, true);
    GEditor->SelectActor(Protected, true, false, true);
    GEditor->SelectActor(Editable, true, true, true);

    const FString MapPath = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ArtFlowDemo.umap"));
    if (!FEditorFileUtils::SaveLevel(World->PersistentLevel, MapPath))
    {
        OutError = TEXT("Could not save the ArtFlow validation map.");
        return false;
    }
    return true;
}

bool PrepareExistingAutomationScene(bool bAllowFixtureUpgrade, FString& OutError)
{
    if (GEditor == nullptr || GEditor->GetEditorWorldContext().World() == nullptr)
    {
        OutError = TEXT("The ArtFlow editor world is unavailable.");
        return false;
    }
    UWorld* World = GEditor->GetEditorWorldContext().World();
    if (World->GetOutermost()->GetName() != TEXT("/Game/ArtFlowDemo"))
    {
        OutError = FString::Printf(TEXT("Expected the project-owned /Game/ArtFlowDemo fixture, got %s."), *World->GetOutermost()->GetName());
        return false;
    }

    ACameraActor* Camera = nullptr;
    AActor* Protected = nullptr;
    AActor* Editable = nullptr;
    AActor* Light = nullptr;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (It->GetActorLabel() == TEXT("ArtFlow_Camera")) Camera = Cast<ACameraActor>(*It);
        if (It->ActorHasTag(ProtectedTag) && Protected == nullptr) Protected = *It;
        if (It->ActorHasTag(EditableTag) && Editable == nullptr) Editable = *It;
        if (It->FindComponentByClass<ULightComponent>() != nullptr && Light == nullptr) Light = *It;
    }
    if (Camera == nullptr || Protected == nullptr || Editable == nullptr || Light == nullptr)
    {
        OutError = TEXT("ArtFlowDemo is missing its camera, protected actor, editable actor or light.");
        return false;
    }

    UPCGComponent* PCGComponent = Editable->FindComponentByClass<UPCGComponent>();
    if (PCGComponent == nullptr && bAllowFixtureUpgrade)
    {
        UPCGGraph* Graph = LoadOrCreateDemoPCGGraph(OutError);
        if (Graph == nullptr) return false;
        PCGComponent = NewObject<UPCGComponent>(Editable, TEXT("PCG_ArtFlowScatter"), RF_Transactional);
        Editable->Modify();
        Editable->AddInstanceComponent(PCGComponent);
        PCGComponent->SetGraph(Graph);
        PCGComponent->Seed = 240827;
        PCGComponent->GenerationTrigger = EPCGComponentGenerationTrigger::GenerateOnDemand;
        PCGComponent->RegisterComponent();
        const FString MapPath = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("ArtFlowDemo.umap"));
        if (!FEditorFileUtils::SaveLevel(World->PersistentLevel, MapPath))
        {
            OutError = TEXT("Could not save the one-time project fixture PCG upgrade.");
            return false;
        }
    }
    if (PCGComponent == nullptr || PCGComponent->GetGraph() == nullptr)
    {
        OutError = bAllowFixtureUpgrade
            ? TEXT("The one-time PCG fixture upgrade did not produce a valid component.")
            : TEXT("ArtFlowDemo has no approved PCG component; run the project-owned fixture preparation first.");
        return false;
    }

    GEditor->SelectNone(false, true, false);
    GEditor->SelectActor(Camera, true, false, true);
    GEditor->SelectActor(Protected, true, false, true);
    GEditor->SelectActor(Editable, true, true, true);
    return true;
}

void WriteAutomationResult(bool bSuccess, const FString& ArchivePath, const FString& Error)
{
    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), bSuccess);
    Result->SetStringField(TEXT("archive_path"), ArchivePath);
    Result->SetStringField(TEXT("error"), Error);
    Result->SetStringField(TEXT("completed_at"), FDateTime::UtcNow().ToIso8601());
    FString Text;
    FJsonSerializer::Serialize(Result.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    const FString ResultPath = FPaths::Combine(GetBridgeRoot(), TEXT("automation-result.json"));
    IFileManager::Get().MakeDirectory(*GetBridgeRoot(), true);
    FFileHelper::SaveStringToFile(Text, *ResultPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}
} // namespace ArtFlowSceneBridge

void FArtFlowSceneBridgeModule::StartupModule()
{
    ArtFlowSceneBridge::RecoverInterruptedExports();
    UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FArtFlowSceneBridgeModule::RegisterMenus));
    if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowCreateDemoAndExport")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowPrepareDemo")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowDryRunExport")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowExecuteStage")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowPublishStage")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowDiscardStage")))
    {
        AutomationTickHandle = FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateRaw(this, &FArtFlowSceneBridgeModule::TickAutomation), 1.0f);
    }
}

void FArtFlowSceneBridgeModule::ShutdownModule()
{
    if (AutomationTickHandle.IsValid())
    {
        FTSTicker::GetCoreTicker().RemoveTicker(AutomationTickHandle);
        AutomationTickHandle.Reset();
    }
    UToolMenus::UnRegisterStartupCallback(this);
    UToolMenus::UnregisterOwner(this);
}

void FArtFlowSceneBridgeModule::RegisterMenus()
{
    FToolMenuOwnerScoped Owner(this);
    UToolMenu* Menu = UToolMenus::Get()->ExtendMenu(TEXT("LevelEditor.MainMenu.Tools"));
    FToolMenuSection& Section = Menu->FindOrAddSection(TEXT("ArtFlow"), LOCTEXT("ArtFlowSection", "ArtFlow"));
    Section.AddMenuEntry(
        TEXT("ArtFlowExportScenePackage"),
        LOCTEXT("ExportLabel", "Export ArtFlow Scene Package"),
        LOCTEXT("ExportTooltip", "Capture the selected camera and tagged region actors into an atomic, hashed Scene Package."),
        FSlateIcon(),
        FUIAction(FExecuteAction::CreateRaw(this, &FArtFlowSceneBridgeModule::ExportSelectedScene)));
    Section.AddMenuEntry(
        TEXT("ArtFlowReviewLastExport"),
        LOCTEXT("ReviewLabel", "Show Last ArtFlow Export"),
        LOCTEXT("ReviewTooltip", "Show the last exported package path. Export is complete and does not wait for approval."),
        FSlateIcon(),
        FUIAction(FExecuteAction::CreateRaw(this, &FArtFlowSceneBridgeModule::ReviewLastExport)));
}

void FArtFlowSceneBridgeModule::ExportSelectedScene()
{
    FString Error;
    FString ArchivePath;
    if (ArtFlowSceneBridge::ExportSelection(ArchivePath, Error))
    {
        LastExportPath = ArchivePath;
        FMessageDialog::Open(EAppMsgType::Ok, FText::Format(LOCTEXT("ExportSuccess", "Scene Package exported successfully. ArtFlow Agent may consume it autonomously:\n{0}"), FText::FromString(ArchivePath)));
    }
    else
    {
        FMessageDialog::Open(EAppMsgType::Ok, FText::Format(LOCTEXT("ExportFailure", "Scene Package export failed closed:\n{0}"), FText::FromString(Error)));
    }
}

void FArtFlowSceneBridgeModule::ReviewLastExport() const
{
    const FString Message = LastExportPath.IsEmpty()
        ? TEXT("No Scene Package has been exported in this editor session.")
        : FString::Printf(TEXT("Last completed Scene Package (no approval pending):\n%s"), *LastExportPath);
    FMessageDialog::Open(EAppMsgType::Ok, FText::FromString(Message));
}

bool FArtFlowSceneBridgeModule::TickAutomation(float DeltaTime)
{
    if (bStageGenerationPending)
    {
        if (StagePCGComponent.IsValid() && StagePCGComponent->IsGenerating())
        {
            return true;
        }
        bStageGenerationPending = false;
        FString Error;
        FString ReceiptPath;
        const bool bSuccess = ArtFlowSceneBridge::FinalizeCandidateExecution(bStageReconciled, StageSourceHash, StageProtectedHash, ReceiptPath, Error);
        ArtFlowSceneBridge::WriteAutomationResult(bSuccess, ReceiptPath, Error);
        UE_LOG(LogArtFlowSceneBridge, Display, TEXT("ARTFLOW_STAGE_RESULT success=%s receipt=%s error=%s"), bSuccess ? TEXT("true") : TEXT("false"), *ReceiptPath, *Error);
        FPlatformMisc::RequestExit(false);
        return false;
    }
    if (bAutomationHandled || GEditor == nullptr || GEditor->GetEditorWorldContext().World() == nullptr)
    {
        return true;
    }
    bAutomationHandled = true;
    FString Error;
    FString ArchivePath;
    const bool bPrepareOnly = FParse::Param(FCommandLine::Get(), TEXT("ArtFlowPrepareDemo"));
    bool bSuccess = false;
    if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowPublishStage")) || FParse::Param(FCommandLine::Get(), TEXT("ArtFlowDiscardStage")))
    {
        const bool bPublish = FParse::Param(FCommandLine::Get(), TEXT("ArtFlowPublishStage"));
        bSuccess = ArtFlowSceneBridge::ExecuteStageDisposition(bPublish, ArchivePath, Error);
    }
    else if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowExecuteStage")))
    {
        UPCGComponent* Component = nullptr;
        bSuccess = ArtFlowSceneBridge::StartCandidateExecution(Component, bStageReconciled, StageSourceHash, StageProtectedHash, Error);
        if (bSuccess)
        {
            StagePCGComponent = Component;
            bStageGenerationPending = true;
            return true;
        }
    }
    else if (bPrepareOnly)
    {
        bSuccess = ArtFlowSceneBridge::PrepareExistingAutomationScene(true, Error);
    }
    else if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowDryRunExport")))
    {
        bSuccess = ArtFlowSceneBridge::PrepareExistingAutomationScene(false, Error) &&
            ArtFlowSceneBridge::ExportSelection(ArchivePath, Error);
    }
    else
    {
        bSuccess = ArtFlowSceneBridge::CreateAutomationScene(Error) && ArtFlowSceneBridge::ExportSelection(ArchivePath, Error);
    }
    if (bSuccess)
    {
        LastExportPath = ArchivePath;
    }
    ArtFlowSceneBridge::WriteAutomationResult(bSuccess, ArchivePath, Error);
    UE_LOG(LogArtFlowSceneBridge, Display, TEXT("ARTFLOW_AUTOMATION_RESULT success=%s archive=%s error=%s"), bSuccess ? TEXT("true") : TEXT("false"), *ArchivePath, *Error);
    FPlatformMisc::RequestExit(false);
    return false;
}

IMPLEMENT_MODULE(FArtFlowSceneBridgeModule, ArtFlowSceneBridge)

#undef LOCTEXT_NAMESPACE
