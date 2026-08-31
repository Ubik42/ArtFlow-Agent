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
#include "Materials/MaterialInterface.h"
#include "Engine/TextureRenderTarget2D.h"
#include "EngineUtils.h"
#include "FileHelpers.h"
#include "FileUtilities/ZipArchiveWriter.h"
#include "Framework/Notifications/NotificationManager.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformProcess.h"
#include "ImageCore.h"
#include "ImageUtils.h"
#include "HttpModule.h"
#include "Interfaces/IHttpResponse.h"
#include "Interfaces/IPluginManager.h"
#include "Json.h"
#include "Misc/App.h"
#include "Misc/Base64.h"
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
#include "Math/RotationMatrix.h"
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
#include "Widgets/Notifications/SNotificationList.h"

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
    FString ArtFlowEndpoint = TEXT("http://127.0.0.1:8796");
    TArray<FString> SessionDomains = {TEXT("image"), TEXT("asset"), TEXT("pcg"), TEXT("lighting")};
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
    Root->TryGetStringField(TEXT("artflow_endpoint"), OutRequest.ArtFlowEndpoint);
    if (Root->HasField(TEXT("session_domains")))
    {
        OutRequest.SessionDomains.Reset();
        if (!ReadStringArray(TEXT("session_domains"), OutRequest.SessionDomains))
        {
            return false;
        }
    }
    FString EndpointOverride;
    if (FParse::Value(FCommandLine::Get(), TEXT("ArtFlowEndpoint="), EndpointOverride))
    {
        OutRequest.ArtFlowEndpoint = EndpointOverride;
    }
    return ReadStringArray(TEXT("preserve"), OutRequest.Preserve) &&
        ReadStringArray(TEXT("prohibit"), OutRequest.Prohibit);
}

bool NormalizeLoopbackOrigin(const FString& Candidate, FString& OutOrigin, FString& OutError)
{
    OutOrigin = Candidate.TrimStartAndEnd();
    while (OutOrigin.EndsWith(TEXT("/")))
    {
        OutOrigin.LeftChopInline(1);
    }
    FString PortText;
    if (OutOrigin.StartsWith(TEXT("http://127.0.0.1:"), ESearchCase::IgnoreCase))
    {
        PortText = OutOrigin.Mid(17);
    }
    else if (OutOrigin.StartsWith(TEXT("http://localhost:"), ESearchCase::IgnoreCase))
    {
        PortText = OutOrigin.Mid(17);
    }
    else
    {
        OutError = TEXT("ArtFlow endpoint must be an explicit localhost HTTP origin.");
        return false;
    }
    if (PortText.IsEmpty() || !PortText.IsNumeric() || PortText.Len() > 5)
    {
        OutError = TEXT("ArtFlow endpoint must contain only a valid localhost port.");
        return false;
    }
    const int32 Port = FCString::Atoi(*PortText);
    if (Port < 1 || Port > 65535)
    {
        OutError = TEXT("ArtFlow endpoint port is outside the valid range.");
        return false;
    }
    return true;
}

bool IsSha256(const FString& Value)
{
    if (Value.Len() != 64)
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!FChar::IsHexDigit(Character) || FChar::IsUpper(Character))
        {
            return false;
        }
    }
    return true;
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

bool StartSessionCandidateExecution(
    const FJsonObject& Plan,
    UPCGComponent*& OutPCG,
    bool& OutReconciled,
    FString& OutCandidatePackage,
    FString& OutPlanId,
    FString& OutPlanSha,
    FString& OutStageRequestSha,
    FString& OutSourceHash,
    FString& OutProtectedHash,
    FString& OutError)
{
    UWorld* SourceWorld = GEditor == nullptr ? nullptr : GEditor->GetEditorWorldContext().World();
    FString Schema;
    FString SourceScene;
    if (SourceWorld == nullptr ||
        !Plan.TryGetStringField(TEXT("schema_id"), Schema) ||
        Schema != TEXT("artflow-scene-candidate-plan/1") ||
        !Plan.TryGetStringField(TEXT("plan_id"), OutPlanId) ||
        !Plan.TryGetStringField(TEXT("plan_sha256"), OutPlanSha) ||
        !Plan.TryGetStringField(TEXT("stage_request_sha256"), OutStageRequestSha) ||
        !Plan.TryGetStringField(TEXT("source_scene"), SourceScene) ||
        !Plan.TryGetStringField(TEXT("candidate_destination"), OutCandidatePackage) ||
        !IsSha256(OutPlanSha) || !IsSha256(OutStageRequestSha) ||
        SourceWorld->GetOutermost()->GetName() != SourceScene ||
        !OutCandidatePackage.StartsWith(TEXT("/Game/ArtFlow/Sessions/AF_")) ||
        !OutCandidatePackage.Contains(TEXT("/Candidates/C_")) ||
        OutCandidatePackage.Contains(TEXT("..")))
    {
        OutError = TEXT("Candidate plan identity, source scene or destination is invalid.");
        return false;
    }

    const TArray<TSharedPtr<FJsonValue>>* Operations = nullptr;
    if (!Plan.TryGetArrayField(TEXT("operations"), Operations) || Operations == nullptr ||
        (Operations->Num() != 2 && Operations->Num() != 4 && Operations->Num() != 5))
    {
        OutError = TEXT("Candidate plan must contain the registered scene operations.");
        return false;
    }
    FString PCGActorId;
    FString PCGActorLabel;
    FString PCGFingerprint;
    FString PCGComponentId;
    FString PCGGraphPath;
    int32 PCGSeed = -1;
    int32 MaxInstances = 0;
    FString LightActorId;
    FString LightActorLabel;
    FString LightFingerprint;
    double LightIntensity = -1.0;
    double LightTemperature = -1.0;
    FString MaterialActorId;
    FString MaterialActorLabel;
    FString MaterialFingerprint;
    FString MaterialPath;
    FString CapabilitySnapshotSha;
    FString GenerationReceiptSha;
    FString MaterialImportRequestSha;
    FString AssetSetId;
    TArray<FString> ApprovedAssetPaths;
    TArray<FString> ApprovedAssetShas;
    FString VisualSourceSha;
    FString VisualArtifactSha;
    FString VisualReceiptSha;
    for (const TSharedPtr<FJsonValue>& Value : *Operations)
    {
        const TSharedPtr<FJsonObject>* Operation = nullptr;
        FString Type;
        FString ToolName;
        if (!Value.IsValid() || !Value->TryGetObject(Operation) || Operation == nullptr ||
            !(*Operation)->TryGetStringField(TEXT("operation_type"), Type) ||
            !(*Operation)->TryGetStringField(TEXT("tool_name"), ToolName))
        {
            OutError = TEXT("Candidate plan contains a malformed registered tool call.");
            return false;
        }
        if (Type == TEXT("apply_pcg_layout") && ToolName == TEXT("unreal.pcg.layout.apply"))
        {
            double Seed = -1.0;
            double Budget = 0.0;
            if (!(*Operation)->TryGetStringField(TEXT("target_actor_id"), PCGActorId) ||
                !(*Operation)->TryGetStringField(TEXT("target_actor_label"), PCGActorLabel) ||
                !(*Operation)->TryGetStringField(TEXT("expected_source_fingerprint"), PCGFingerprint) ||
                !(*Operation)->TryGetStringField(TEXT("component_id"), PCGComponentId) ||
                !(*Operation)->TryGetStringField(TEXT("approved_graph_path"), PCGGraphPath) ||
                !(*Operation)->TryGetNumberField(TEXT("seed"), Seed) ||
                !(*Operation)->TryGetNumberField(TEXT("max_generated_instances"), Budget) ||
                !IsSha256(PCGFingerprint) ||
                !PCGGraphPath.StartsWith(TEXT("/Game/ArtFlow/PCG/")) ||
                Seed < 0 || Seed > 2147483647.0 || Budget < 1 || Budget > 10000)
            {
                OutError = TEXT("Candidate PCG tool call failed its typed parameter bounds.");
                return false;
            }
            PCGSeed = static_cast<int32>(Seed);
            MaxInstances = static_cast<int32>(Budget);
        }
        else if (Type == TEXT("set_lighting_rig") && ToolName == TEXT("unreal.lighting.rig.patch"))
        {
            if (!(*Operation)->TryGetStringField(TEXT("target_actor_id"), LightActorId) ||
                !(*Operation)->TryGetStringField(TEXT("target_actor_label"), LightActorLabel) ||
                !(*Operation)->TryGetStringField(TEXT("expected_source_fingerprint"), LightFingerprint) ||
                !(*Operation)->TryGetNumberField(TEXT("intensity"), LightIntensity) ||
                !(*Operation)->TryGetNumberField(TEXT("temperature_kelvin"), LightTemperature) ||
                !IsSha256(LightFingerprint) || LightIntensity < 0 || LightIntensity > 1000000 ||
                LightTemperature < 1000 || LightTemperature > 20000)
            {
                OutError = TEXT("Candidate lighting tool call failed its typed parameter bounds.");
                return false;
            }
        }
        else if (Type == TEXT("bind_verified_pbr_material") &&
            ToolName == TEXT("unreal.material.verified_pbr.bind"))
        {
            if (!(*Operation)->TryGetStringField(TEXT("target_actor_id"), MaterialActorId) ||
                !(*Operation)->TryGetStringField(TEXT("target_actor_label"), MaterialActorLabel) ||
                !(*Operation)->TryGetStringField(TEXT("expected_source_fingerprint"), MaterialFingerprint) ||
                !(*Operation)->TryGetStringField(TEXT("capability_snapshot_sha256"), CapabilitySnapshotSha) ||
                !(*Operation)->TryGetStringField(TEXT("generation_receipt_sha256"), GenerationReceiptSha) ||
                !(*Operation)->TryGetStringField(TEXT("unreal_import_request_sha256"), MaterialImportRequestSha) ||
                !(*Operation)->TryGetStringField(TEXT("material_instance_path"), MaterialPath) ||
                !IsSha256(MaterialFingerprint) || !IsSha256(CapabilitySnapshotSha) ||
                !IsSha256(GenerationReceiptSha) || !IsSha256(MaterialImportRequestSha) ||
                !MaterialPath.StartsWith(TEXT("/Game/ArtFlow/Generated/")))
            {
                OutError = TEXT("Candidate material tool call failed its provenance or namespace bounds.");
                return false;
            }
        }
        else if (Type == TEXT("bind_project_asset_set") &&
            ToolName == TEXT("unreal.project_assets.bind"))
        {
            if (!(*Operation)->TryGetStringField(TEXT("asset_set_id"), AssetSetId) ||
                !(*Operation)->TryGetStringArrayField(TEXT("approved_asset_paths"), ApprovedAssetPaths) ||
                !(*Operation)->TryGetStringArrayField(TEXT("approved_asset_sha256s"), ApprovedAssetShas) ||
                ApprovedAssetPaths.Num() != 1 || ApprovedAssetShas.Num() != 1 ||
                !ApprovedAssetPaths[0].StartsWith(TEXT("/Game/ArtFlow/Props/")) ||
                !IsSha256(ApprovedAssetShas[0]))
            {
                OutError = TEXT("Candidate project asset set failed its typed allowlist bounds.");
                return false;
            }
        }
        else if (Type == TEXT("bind_visual_target") &&
            ToolName == TEXT("codex.image.visual_target.bind"))
        {
            const TArray<TSharedPtr<FJsonValue>>* Preserve = nullptr;
            if (!(*Operation)->TryGetStringField(TEXT("source_render_sha256"), VisualSourceSha) ||
                !(*Operation)->TryGetStringField(TEXT("artifact_sha256"), VisualArtifactSha) ||
                !(*Operation)->TryGetStringField(TEXT("receipt_sha256"), VisualReceiptSha) ||
                !(*Operation)->TryGetArrayField(TEXT("preserve"), Preserve) || Preserve == nullptr ||
                Preserve->Num() < 1 || !IsSha256(VisualSourceSha) ||
                !IsSha256(VisualArtifactSha) || !IsSha256(VisualReceiptSha))
            {
                OutError = TEXT("Candidate visual target failed its content binding.");
                return false;
            }
        }
        else
        {
            OutError = TEXT("Candidate plan requested an unregistered Unreal tool.");
            return false;
        }
    }
    const bool bHasCrossPipelineDomains = !MaterialPath.IsEmpty() || !AssetSetId.IsEmpty();
    if (PCGActorId.IsEmpty() || LightActorId.IsEmpty() ||
        (bHasCrossPipelineDomains && (MaterialPath.IsEmpty() || AssetSetId.IsEmpty())))
    {
        OutError = TEXT("Candidate plan omitted a required registered domain tool.");
        return false;
    }

    const FString SourceFilename = FPackageName::LongPackageNameToFilename(
        SourceScene, FPackageName::GetMapPackageExtension());
    if (!HashFile(SourceFilename, OutSourceHash, OutError))
    {
        return false;
    }
    AActor* SourcePCGActor = FindActorByLabel(SourceWorld, PCGActorLabel);
    AActor* SourceLightActor = FindActorByLabel(SourceWorld, LightActorLabel);
    AActor* SourceProtected = FindActorByLabel(SourceWorld, TEXT("Protected_Blockout"));
    const auto ActorId = [](const AActor* Actor)
    {
        return Actor == nullptr
            ? FString()
            : Actor->GetActorGuid().ToString(EGuidFormats::Digits).ToLower();
    };
    if (ActorId(SourcePCGActor) != PCGActorId || ActorId(SourceLightActor) != LightActorId ||
        SourceProtected == nullptr || ActorFingerprint(SourcePCGActor) != PCGFingerprint ||
        ActorFingerprint(SourceLightActor) != LightFingerprint ||
        (bHasCrossPipelineDomains &&
            (MaterialActorId != PCGActorId || MaterialActorLabel != PCGActorLabel ||
             MaterialFingerprint != PCGFingerprint)))
    {
        OutError = TEXT("Candidate plan source Actor identity or fingerprint is stale.");
        return false;
    }
    OutProtectedHash = ProtectedSemanticFingerprint(SourceProtected);

    const FString CandidateFilename = FPackageName::LongPackageNameToFilename(
        OutCandidatePackage, FPackageName::GetMapPackageExtension());
    const bool bCandidateExists = IFileManager::Get().FileExists(*CandidateFilename);
    if (!bCandidateExists)
    {
        IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get();
        UWorld* Duplicated = Cast<UWorld>(AssetTools.DuplicateAsset(
            FPackageName::GetLongPackageAssetName(OutCandidatePackage),
            FPackageName::GetLongPackagePath(OutCandidatePackage),
            SourceWorld));
        if (Duplicated == nullptr)
        {
            OutError = TEXT("Could not duplicate the source into the request-derived candidate namespace.");
            return false;
        }
        UPackage* CandidatePackageObject = Duplicated->GetOutermost();
        FSavePackageArgs SaveArgs;
        SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
        SaveArgs.SaveFlags = SAVE_NoError;
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(CandidateFilename), true);
        if (!UPackage::SavePackage(CandidatePackageObject, Duplicated, *CandidateFilename, SaveArgs))
        {
            OutError = TEXT("Could not persist the request-derived candidate level.");
            return false;
        }
        Duplicated = nullptr;
        FText UnloadError;
        if (!UPackageTools::UnloadPackages({CandidatePackageObject}, UnloadError, true))
        {
            OutError = TEXT("Could not release the duplicated candidate before loading it.");
            return false;
        }
    }
    if (!FEditorFileUtils::LoadMap(CandidateFilename, false, false))
    {
        OutError = TEXT("Could not load the request-derived candidate level.");
        return false;
    }
    UWorld* CandidateWorld = GEditor->GetEditorWorldContext().World();
    AActor* CandidatePCGActor = FindActorByLabel(CandidateWorld, PCGActorLabel);
    AActor* CandidateLightActor = FindActorByLabel(CandidateWorld, LightActorLabel);
    AActor* CandidateProtected = FindActorByLabel(CandidateWorld, TEXT("Protected_Blockout"));
    OutPCG = CandidatePCGActor == nullptr ? nullptr : CandidatePCGActor->FindComponentByClass<UPCGComponent>();
    ULightComponent* Light = CandidateLightActor == nullptr
        ? nullptr
        : CandidateLightActor->FindComponentByClass<ULightComponent>();
    UPCGGraph* Graph = LoadObject<UPCGGraph>(nullptr, *PCGGraphPath);
    UMaterialInterface* Material = bHasCrossPipelineDomains
        ? LoadObject<UMaterialInterface>(nullptr, *MaterialPath)
        : nullptr;
    UStaticMesh* ApprovedAsset = bHasCrossPipelineDomains
        ? LoadObject<UStaticMesh>(nullptr, *ApprovedAssetPaths[0])
        : nullptr;
    FString ApprovedAssetHash;
    if (bHasCrossPipelineDomains)
    {
        const FString AssetPackage = FPackageName::ObjectPathToPackageName(ApprovedAssetPaths[0]);
        const FString AssetFilename = FPackageName::LongPackageNameToFilename(
            AssetPackage, FPackageName::GetAssetPackageExtension());
        if (!HashFile(AssetFilename, ApprovedAssetHash, OutError) ||
            ApprovedAssetHash != ApprovedAssetShas[0])
        {
            OutError = TEXT("Approved project asset bytes no longer match the candidate plan.");
            return false;
        }
    }
    if (CandidateProtected == nullptr || OutPCG == nullptr || Light == nullptr || Graph == nullptr ||
        ProtectedSemanticFingerprint(CandidateProtected) != OutProtectedHash ||
        (bHasCrossPipelineDomains && (Material == nullptr || ApprovedAsset == nullptr)))
    {
        OutError = FString::Printf(
            TEXT("Candidate target validation failed: pcg_actor=%s light_actor=%s protected=%s pcg_component=%s light_component=%s graph=%s protected_hash=%s."),
            CandidatePCGActor == nullptr ? TEXT("missing") : TEXT("derived"),
            CandidateLightActor == nullptr ? TEXT("missing") : TEXT("derived"),
            CandidateProtected == nullptr ? TEXT("missing") : TEXT("present"),
            OutPCG == nullptr ? TEXT("missing") : TEXT("present"),
            Light == nullptr ? TEXT("missing") : TEXT("present"),
            Graph == nullptr ? TEXT("missing") : TEXT("present"),
            CandidateProtected != nullptr && ProtectedSemanticFingerprint(CandidateProtected) == OutProtectedHash
                ? TEXT("match") : TEXT("mismatch"));
        return false;
    }
    const int32 ExistingInstances = CountGeneratedInstances(CandidateWorld);
    UStaticMeshComponent* CandidateMesh = CandidatePCGActor == nullptr
        ? nullptr
        : CandidatePCGActor->FindComponentByClass<UStaticMeshComponent>();
    const bool bMaterialMatches = !bHasCrossPipelineDomains ||
        (CandidateMesh != nullptr && CandidateMesh->GetMaterial(0) == Material);
    const bool bExactExistingResult = bCandidateExists && ExistingInstances == 12 &&
        OutPCG->GetGraph() == Graph && OutPCG->Seed == PCGSeed &&
        FMath::IsNearlyEqual(Light->Intensity, static_cast<float>(LightIntensity)) &&
        Light->bUseTemperature &&
        FMath::IsNearlyEqual(Light->Temperature, static_cast<float>(LightTemperature)) &&
        bMaterialMatches;
    if (bCandidateExists && !bExactExistingResult)
    {
        OutError = TEXT("An existing candidate does not match the content-bound plan; refusing overwrite.");
        return false;
    }
    OutReconciled = bExactExistingResult;
    if (!OutReconciled)
    {
        OutPCG->SetGraph(Graph);
        OutPCG->Seed = PCGSeed;
        Light->SetIntensity(static_cast<float>(LightIntensity));
        Light->SetUseTemperature(true);
        Light->SetTemperature(static_cast<float>(LightTemperature));
        if (bHasCrossPipelineDomains)
        {
            if (CandidateMesh == nullptr)
            {
                OutError = TEXT("Candidate material target has no StaticMeshComponent.");
                return false;
            }
            CandidateMesh->SetMaterial(0, Material);
            CandidatePCGActor->Tags.AddUnique(TEXT("ArtFlow.PBR"));
            CandidatePCGActor->Tags.AddUnique(FName(*AssetSetId));
        }
        OutPCG->CleanupLocalImmediate(true, true);
        OutPCG->GenerateLocal(true);
    }
    if (ExistingInstances > MaxInstances)
    {
        OutError = TEXT("Candidate already exceeds the plan instance budget.");
        return false;
    }
    return true;
}

bool FinalizeSessionCandidateExecution(
    const bool bReconciled,
    const FString& CandidatePackagePath,
    const FString& PlanId,
    const FString& PlanSha,
    const FString& StageRequestSha,
    const FString& SourceHash,
    const FString& ProtectedHash,
    FString& OutReceiptPath,
    FString& OutError)
{
    UWorld* World = GEditor == nullptr ? nullptr : GEditor->GetEditorWorldContext().World();
    if (World == nullptr || World->GetOutermost()->GetName() != CandidatePackagePath)
    {
        OutError = TEXT("The candidate world changed before reconciliation.");
        return false;
    }
    const int32 InstanceCount = CountGeneratedInstances(World);
    AActor* Protected = FindActorByLabel(World, TEXT("Protected_Blockout"));
    AActor* Camera = FindActorByLabel(World, TEXT("ArtFlow_Camera"));
    if (InstanceCount != 12 || Protected == nullptr || Camera == nullptr ||
        ProtectedSemanticFingerprint(Protected) != ProtectedHash)
    {
        OutError = TEXT("Candidate output or protected invariant failed reconciliation.");
        return false;
    }
    const FString CandidateFilename = FPackageName::LongPackageNameToFilename(
        CandidatePackagePath, FPackageName::GetMapPackageExtension());
    if (!FEditorFileUtils::SaveLevel(World->PersistentLevel, CandidateFilename))
    {
        OutError = TEXT("Could not save the isolated candidate level.");
        return false;
    }
    FString CandidateSha;
    FString SourceAfter;
    const FString SourceFilename = FPackageName::LongPackageNameToFilename(
        TEXT("/Game/ArtFlowDemo"), FPackageName::GetMapPackageExtension());
    if (!HashFile(CandidateFilename, CandidateSha, OutError) ||
        !HashFile(SourceFilename, SourceAfter, OutError) || SourceAfter != SourceHash)
    {
        OutError = TEXT("Candidate save changed the source level or failed content hashing.");
        return false;
    }
    const FString OutputRoot = FPaths::Combine(GetBridgeRoot(), TEXT("SceneCandidates"), PlanId);
    IFileManager::Get().MakeDirectory(*OutputRoot, true);
    const FString BeautyPath = FPaths::Combine(OutputRoot, TEXT("candidate-beauty.png"));
    FCaptureRequest Request;
    if (!LoadCaptureRequest(Request, OutError) ||
        !CapturePass(World, Cast<ACameraActor>(Camera), Request, SCS_FinalColorLDR, false, BeautyPath, nullptr, {}, OutError))
    {
        return false;
    }
    FString BeautySha;
    if (!HashFile(BeautyPath, BeautySha, OutError))
    {
        return false;
    }
    TSharedPtr<FJsonObject> Receipt = MakeShared<FJsonObject>();
    Receipt->SetStringField(TEXT("schema_id"), TEXT("artflow-session-candidate-execution-receipt/1"));
    Receipt->SetStringField(TEXT("plan_id"), PlanId);
    Receipt->SetStringField(TEXT("plan_sha256"), PlanSha);
    Receipt->SetStringField(TEXT("stage_request_sha256"), StageRequestSha);
    Receipt->SetStringField(TEXT("source_scene"), TEXT("/Game/ArtFlowDemo"));
    Receipt->SetStringField(TEXT("source_level_sha256_before"), SourceHash);
    Receipt->SetStringField(TEXT("source_level_sha256_after"), SourceAfter);
    Receipt->SetBoolField(TEXT("source_level_unchanged"), true);
    Receipt->SetStringField(TEXT("candidate_scene"), CandidatePackagePath);
    Receipt->SetStringField(TEXT("candidate_level_sha256"), CandidateSha);
    Receipt->SetNumberField(TEXT("generated_instance_count"), InstanceCount);
    Receipt->SetBoolField(TEXT("reconciled"), bReconciled);
    Receipt->SetStringField(TEXT("candidate_beauty_path"), BeautyPath);
    Receipt->SetStringField(TEXT("candidate_beauty_sha256"), BeautySha);
    Receipt->SetStringField(TEXT("completed_at"), FDateTime::UtcNow().ToIso8601());
    FString Text;
    FJsonSerializer::Serialize(Receipt.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    OutReceiptPath = FPaths::Combine(OutputRoot, TEXT("candidate-execution-receipt.json"));
    if (!FFileHelper::SaveStringToFile(Text, *OutReceiptPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
    {
        OutError = TEXT("Could not persist the candidate execution receipt.");
        return false;
    }
    return true;
}

bool StartCandidateExecution(UPCGComponent*& OutPCG, bool& OutReconciled, FString& OutSourceHash, FString& OutProtectedHash, FString& OutError, bool bApplyReviewedDelta = true)
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
    if (bApplyReviewedDelta)
    {
        OutPCG->SetGraph(ReviewedGraph);
        OutPCG->Seed = 240827;
        Light->SetIntensity(5.5f);
        Light->SetUseTemperature(true);
        Light->SetTemperature(4200.0f);
    }
    const int32 ExistingInstances = CountGeneratedInstances(CandidateWorld);
    OutReconciled = ExistingInstances == 12;
    if (!OutReconciled && bApplyReviewedDelta)
    {
        OutPCG->CleanupLocalImmediate(true, true);
        OutPCG->GenerateLocal(true);
    }
    else if (!OutReconciled)
    {
        OutError = FString::Printf(TEXT("Capture-only validation found %d instances; expected exactly 12."), ExistingInstances);
        return false;
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
    FString ValidationPath;
    FString ValidationHash;
    FString M9RequestId;
    FString M9RequestSha;
    if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowMultiView")))
    {
        const FString M9RequestPath = FPlatformMisc::GetEnvironmentVariable(TEXT("ARTFLOW_M9_REQUEST"));
        FString M9RequestText;
        TSharedPtr<FJsonObject> M9Request;
        if (M9RequestPath.IsEmpty() ||
            !FFileHelper::LoadFileToString(M9RequestText, *M9RequestPath) ||
            !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(M9RequestText), M9Request) ||
            !M9Request.IsValid() ||
            !M9Request->TryGetStringField(TEXT("request_id"), M9RequestId) ||
            !M9Request->TryGetStringField(TEXT("request_sha256"), M9RequestSha) ||
            M9Request->GetStringField(TEXT("candidate_scene_path")) != CandidatePackage)
        {
            OutError = TEXT("M9 multi-view capture requires a valid request bound to the candidate scene.");
            return false;
        }
        const FVector ValidationLocation(-620.0, -650.0, 330.0);
        const FVector ValidationTarget(0.0, 40.0, 105.0);
        FActorSpawnParameters SpawnParameters;
        SpawnParameters.ObjectFlags |= RF_Transient;
        ACameraActor* ValidationCamera = World->SpawnActor<ACameraActor>(
            ValidationLocation,
            FRotationMatrix::MakeFromX(ValidationTarget - ValidationLocation).Rotator(),
            SpawnParameters);
        if (ValidationCamera == nullptr)
        {
            OutError = TEXT("Could not create the transient M9 validation camera.");
            return false;
        }
        ValidationCamera->SetActorLabel(TEXT("ArtFlow_M9_ValidationCamera"));
        ValidationCamera->GetCameraComponent()->FieldOfView =
            Cast<ACameraActor>(Camera)->GetCameraComponent()->FieldOfView;
        ValidationPath = FPaths::Combine(OutputRoot, TEXT("candidate-validation-camera.png"));
        const bool bValidationCaptured = CapturePass(
            World,
            ValidationCamera,
            Request,
            SCS_FinalColorLDR,
            false,
            ValidationPath,
            nullptr,
            {},
            OutError);
        World->DestroyActor(ValidationCamera);
        if (!bValidationCaptured || !HashFile(ValidationPath, ValidationHash, OutError))
        {
            return false;
        }
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
    if (!ValidationPath.IsEmpty())
    {
        TSharedPtr<FJsonObject> MultiView = MakeShared<FJsonObject>();
        MultiView->SetStringField(TEXT("schema_id"), TEXT("multi-view-capture-receipt/1"));
        MultiView->SetStringField(TEXT("request_id"), M9RequestId);
        MultiView->SetStringField(TEXT("request_sha256"), M9RequestSha);
        MultiView->SetStringField(TEXT("candidate_scene_path"), CandidatePackage);
        MultiView->SetStringField(TEXT("authored_camera_label"), TEXT("ArtFlow_Camera"));
        MultiView->SetStringField(TEXT("authored_render_path"), BeautyPath);
        MultiView->SetStringField(TEXT("authored_render_sha256"), BeautyHash);
        MultiView->SetStringField(TEXT("validation_camera_label"), TEXT("ArtFlow_M9_ValidationCamera"));
        MultiView->SetArrayField(
            TEXT("validation_camera_location"),
            {MakeShared<FJsonValueNumber>(-620.0), MakeShared<FJsonValueNumber>(-650.0), MakeShared<FJsonValueNumber>(330.0)});
        MultiView->SetArrayField(
            TEXT("validation_camera_target"),
            {MakeShared<FJsonValueNumber>(0.0), MakeShared<FJsonValueNumber>(40.0), MakeShared<FJsonValueNumber>(105.0)});
        MultiView->SetStringField(TEXT("validation_render_path"), ValidationPath);
        MultiView->SetStringField(TEXT("validation_render_sha256"), ValidationHash);
        MultiView->SetStringField(TEXT("source_scene_sha256_before"), SourceHash);
        MultiView->SetStringField(TEXT("source_scene_sha256_after"), SourceAfter);
        MultiView->SetStringField(TEXT("protected_semantic_fingerprint"), ProtectedHash);
        MultiView->SetNumberField(TEXT("generated_instance_count"), InstanceCount);
        MultiView->SetBoolField(TEXT("asset_and_shader_compilation_finished"), true);
        MultiView->SetStringField(TEXT("created_at"), FDateTime::UtcNow().ToIso8601());
        FString MultiViewText;
        FJsonSerializer::Serialize(MultiView.ToSharedRef(), TJsonWriterFactory<>::Create(&MultiViewText));
        const FString MultiViewPath = FPaths::Combine(OutputRoot, TEXT("multi-view-capture-receipt.json"));
        if (!FFileHelper::SaveStringToFile(
                MultiViewText,
                *MultiViewPath,
                FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
        {
            OutError = TEXT("Could not persist the M9 multi-view capture receipt.");
            return false;
        }
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
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowSessionHandshake")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowExecuteSessionCandidate")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowReconcileSessionCandidate")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowPrepareDemo")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowDryRunExport")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowExecuteStage")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowCaptureStage")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowPublishStage")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowDiscardStage")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowLifecycleCallback")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowClaimCandidateWork")))
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
        TEXT("ArtFlowStartSceneSession"),
        LOCTEXT("StartSessionLabel", "启动 ArtFlow 场景任务"),
        LOCTEXT("StartSessionTooltip", "从当前关卡导出可验证场景包，并向本机 ArtFlow Agent 请求类型化候选方案。不会修改当前关卡。"),
        FSlateIcon(),
        FUIAction(FExecuteAction::CreateRaw(this, &FArtFlowSceneBridgeModule::StartSceneSession)));
    Section.AddMenuEntry(
        TEXT("ArtFlowExecuteCurrentCandidate"),
        LOCTEXT("ExecuteCandidateLabel", "执行当前 ArtFlow 候选"),
        LOCTEXT("ExecuteCandidateTooltip", "领取当前 Scene Session 已封存的候选工作项，在隔离关卡执行并把进度回传到场景变更谱。"),
        FSlateIcon(),
        FUIAction(FExecuteAction::CreateRaw(this, &FArtFlowSceneBridgeModule::ExecuteCurrentCandidateWork)));
    Section.AddMenuEntry(
        TEXT("ArtFlowExportScenePackage"),
        LOCTEXT("ExportLabel", "仅导出场景包"),
        LOCTEXT("ExportTooltip", "将选定相机与标记区域导出为原子化、内容哈希绑定的 Scene Package。"),
        FSlateIcon(),
        FUIAction(FExecuteAction::CreateRaw(this, &FArtFlowSceneBridgeModule::ExportSelectedScene)));
    Section.AddMenuEntry(
        TEXT("ArtFlowReviewLastExport"),
        LOCTEXT("ReviewLabel", "查看最近导出"),
        LOCTEXT("ReviewTooltip", "查看本次编辑器会话最近完成的 Scene Package。"),
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

void FArtFlowSceneBridgeModule::StartSceneSession()
{
    FString Error;
    FString ArchivePath;
    if (!ArtFlowSceneBridge::ExportSelection(ArchivePath, Error) ||
        !BeginSceneSessionHandshake(ArchivePath, false, Error))
    {
        FMessageDialog::Open(
            EAppMsgType::Ok,
            FText::Format(
                LOCTEXT("SessionStartFailure", "ArtFlow 场景任务未启动：\n{0}\n\n当前关卡未发生修改。"),
                FText::FromString(Error)));
        return;
    }
    LastExportPath = ArchivePath;
}

void FArtFlowSceneBridgeModule::ExecuteCurrentCandidateWork()
{
    FString Error;
    if (SessionRunId.IsEmpty() || SessionSha256.IsEmpty())
    {
        Error = TEXT("请先从当前关卡启动 ArtFlow 场景任务，再在场景变更谱中把候选交给 Unreal。");
    }
    else
    {
        BeginSceneCandidateWorkDiscovery(false, Error);
    }
    if (!Error.IsEmpty())
    {
        FMessageDialog::Open(
            EAppMsgType::Ok,
            FText::Format(
                LOCTEXT("CandidateWorkStartFailure", "ArtFlow 候选未开始：\n{0}\n\n源关卡未发生修改。"),
                FText::FromString(Error)));
    }
}

bool FArtFlowSceneBridgeModule::BeginSceneSessionHandshake(
    const FString& ArchivePath,
    const bool bAutomation,
    FString& OutError)
{
    if (bSessionHandshakePending)
    {
        OutError = TEXT("An ArtFlow Scene Session handshake is already pending.");
        return false;
    }
    ArtFlowSceneBridge::FCaptureRequest CaptureRequest;
    if (!ArtFlowSceneBridge::LoadCaptureRequest(CaptureRequest, OutError) ||
        !ArtFlowSceneBridge::NormalizeLoopbackOrigin(
            CaptureRequest.ArtFlowEndpoint,
            SessionEndpointOrigin,
            OutError))
    {
        return false;
    }
    UWorld* World = GEditor == nullptr ? nullptr : GEditor->GetEditorWorldContext().World();
    if (World == nullptr || World->WorldType != EWorldType::Editor)
    {
        OutError = TEXT("ArtFlow Scene Session requires an active editor level.");
        return false;
    }
    SessionSourceScene = World->GetOutermost()->GetName();
    SessionSourceLevelPath = FPackageName::LongPackageNameToFilename(
        SessionSourceScene,
        FPackageName::GetMapPackageExtension());
    if (!IFileManager::Get().FileExists(*SessionSourceLevelPath) ||
        !ArtFlowSceneBridge::HashFile(
            SessionSourceLevelPath,
            SessionSourceLevelSha,
            OutError))
    {
        OutError = TEXT("Save the active project-owned level before starting ArtFlow. ") + OutError;
        return false;
    }
    TArray<uint8> ArchiveBytes;
    if (!FFileHelper::LoadFileToArray(ArchiveBytes, *ArchivePath) || ArchiveBytes.IsEmpty() ||
        !ArtFlowSceneBridge::HashBytes(ArchiveBytes, SessionArchiveSha))
    {
        OutError = TEXT("The exported Scene Package could not be read or hashed.");
        return false;
    }
    const TSet<FString> AllowedDomains = {
        TEXT("image"), TEXT("material"), TEXT("asset"), TEXT("pcg"), TEXT("lighting")};
    TSet<FString> UniqueDomains;
    TArray<FString> NormalizedDomains;
    for (FString Domain : CaptureRequest.SessionDomains)
    {
        Domain = Domain.TrimStartAndEnd().ToLower();
        if (!AllowedDomains.Contains(Domain) || UniqueDomains.Contains(Domain))
        {
            OutError = TEXT("ArtFlow session_domains contains an unknown or duplicate domain.");
            return false;
        }
        UniqueDomains.Add(Domain);
        NormalizedDomains.Add(Domain);
    }
    if (UniqueDomains.IsEmpty())
    {
        OutError = TEXT("ArtFlow session_domains cannot be empty.");
        return false;
    }

    FTCHARToUTF8 IntentUtf8(*CaptureRequest.Goal);
    TArray<uint8> IntentBytes;
    IntentBytes.Append(
        reinterpret_cast<const uint8*>(IntentUtf8.Get()),
        IntentUtf8.Length());
    SessionActionId = TEXT("ue-handshake-") + SessionArchiveSha.Left(24);
    SessionArchivePath = ArchivePath;
    bSessionHandshakeAutomation = bAutomation;

    const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> HttpRequest =
        FHttpModule::Get().CreateRequest();
    HttpRequest->SetURL(
        SessionEndpointOrigin + TEXT("/api/agent/scene-sessions/handshake"));
    HttpRequest->SetVerb(TEXT("POST"));
    HttpRequest->SetHeader(TEXT("Content-Type"), TEXT("application/zip"));
    HttpRequest->SetHeader(TEXT("X-Scene-Package-SHA256"), SessionArchiveSha);
    HttpRequest->SetHeader(TEXT("X-ArtFlow-Intent-Base64"), FBase64::Encode(IntentBytes));
    HttpRequest->SetHeader(
        TEXT("X-ArtFlow-Domains"),
        FString::Join(NormalizedDomains, TEXT(",")));
    HttpRequest->SetHeader(TEXT("X-ArtFlow-Action-Id"), SessionActionId);
    HttpRequest->SetContent(ArchiveBytes);
    HttpRequest->SetTimeout(60.0f);
    HttpRequest->OnProcessRequestComplete().BindRaw(
        this,
        &FArtFlowSceneBridgeModule::HandleSceneSessionHandshake);
    bSessionHandshakePending = true;
    if (!HttpRequest->ProcessRequest())
    {
        bSessionHandshakePending = false;
        OutError = TEXT("The localhost ArtFlow request could not be submitted.");
        return false;
    }
    UE_LOG(
        LogArtFlowSceneBridge,
        Display,
        TEXT("ARTFLOW_SESSION_HANDSHAKE_SUBMITTED action=%s archive_sha256=%s source=%s endpoint=%s"),
        *SessionActionId,
        *SessionArchiveSha,
        *SessionSourceScene,
        *SessionEndpointOrigin);
    return true;
}

void FArtFlowSceneBridgeModule::HandleSceneSessionHandshake(
    FHttpRequestPtr Request,
    FHttpResponsePtr Response,
    const bool bConnectedSuccessfully)
{
    static_cast<void>(Request);
    bSessionHandshakePending = false;
    FString Error;
    FString ReceiptPath;
    TSharedPtr<FJsonObject> BackendReceipt;
    const int32 ResponseCode = Response.IsValid() ? Response->GetResponseCode() : 0;
    if (!bConnectedSuccessfully || !Response.IsValid())
    {
        Error = TEXT("The localhost ArtFlow runtime did not return a response.");
    }
    else if (ResponseCode != 200)
    {
        Error = FString::Printf(
            TEXT("ArtFlow rejected the Scene Session handshake (HTTP %d): %s"),
            ResponseCode,
            *Response->GetContentAsString().Left(800));
    }
    else
    {
        const TSharedRef<TJsonReader<>> Reader =
            TJsonReaderFactory<>::Create(Response->GetContentAsString());
        if (!FJsonSerializer::Deserialize(Reader, BackendReceipt) || !BackendReceipt.IsValid())
        {
            Error = TEXT("ArtFlow returned invalid JSON.");
        }
    }

    FString Schema;
    FString HandshakeId;
    FString HandshakeSha;
    FString ActionId;
    FString RunId;
    FString SourceScene;
    FString ScenePackageSha;
    const TSharedPtr<FJsonObject>* Session = nullptr;
    const TSharedPtr<FJsonObject>* StageRequest = nullptr;
    const TSharedPtr<FJsonObject>* CandidatePlan = nullptr;
    if (Error.IsEmpty() &&
        (!BackendReceipt->TryGetStringField(TEXT("schema_id"), Schema) ||
        !BackendReceipt->TryGetStringField(TEXT("handshake_id"), HandshakeId) ||
        !BackendReceipt->TryGetStringField(TEXT("handshake_sha256"), HandshakeSha) ||
        !BackendReceipt->TryGetStringField(TEXT("action_id"), ActionId) ||
        !BackendReceipt->TryGetStringField(TEXT("run_id"), RunId) ||
        !BackendReceipt->TryGetStringField(TEXT("source_scene"), SourceScene) ||
        !BackendReceipt->TryGetStringField(TEXT("scene_package_sha256"), ScenePackageSha) ||
        !BackendReceipt->TryGetObjectField(TEXT("session"), Session) ||
        !BackendReceipt->TryGetObjectField(TEXT("stage_request"), StageRequest)))
    {
        Error = TEXT("ArtFlow handshake receipt is missing required typed fields.");
    }
    FString SessionSchema;
    FString SessionSha;
    FString StageSchema;
    FString StageSessionSha;
    FString StageSceneSha;
    FString StageRequestSha;
    FString CandidateDestination;
    if (Error.IsEmpty())
    {
        (*Session)->TryGetStringField(TEXT("schema_id"), SessionSchema);
        (*Session)->TryGetStringField(TEXT("session_sha256"), SessionSha);
        (*StageRequest)->TryGetStringField(TEXT("schema_id"), StageSchema);
        (*StageRequest)->TryGetStringField(TEXT("session_sha256"), StageSessionSha);
        (*StageRequest)->TryGetStringField(TEXT("scene_package_sha256"), StageSceneSha);
        (*StageRequest)->TryGetStringField(TEXT("request_sha256"), StageRequestSha);
        (*StageRequest)->TryGetStringField(TEXT("candidate_destination"), CandidateDestination);
        if (Schema != TEXT("artflow-scene-session-handshake/1") ||
            SessionSchema != TEXT("artflow-scene-session/1") ||
            StageSchema != TEXT("artflow-scene-stage-request/1") ||
            ActionId != SessionActionId || SourceScene != SessionSourceScene ||
            ScenePackageSha != SessionArchiveSha || StageSceneSha != SessionArchiveSha ||
            !ArtFlowSceneBridge::IsSha256(HandshakeSha) ||
            !ArtFlowSceneBridge::IsSha256(SessionSha) || SessionSha != StageSessionSha ||
            !CandidateDestination.StartsWith(TEXT("/Game/ArtFlow/Sessions/")))
        {
            Error = TEXT("ArtFlow handshake identity or candidate boundary did not match the exact exported scene.");
        }
    }
    if (Error.IsEmpty() && BackendReceipt->HasField(TEXT("candidate_plan")))
    {
        FString CandidatePlanSchema;
        FString CandidatePlanStageSha;
        FString CandidatePlanDestination;
        FString CandidatePlanSource;
        if (!BackendReceipt->TryGetObjectField(TEXT("candidate_plan"), CandidatePlan) ||
            CandidatePlan == nullptr ||
            !(*CandidatePlan)->TryGetStringField(TEXT("schema_id"), CandidatePlanSchema) ||
            !(*CandidatePlan)->TryGetStringField(TEXT("stage_request_sha256"), CandidatePlanStageSha) ||
            !(*CandidatePlan)->TryGetStringField(TEXT("candidate_destination"), CandidatePlanDestination) ||
            !(*CandidatePlan)->TryGetStringField(TEXT("source_scene"), CandidatePlanSource) ||
            CandidatePlanSchema != TEXT("artflow-scene-candidate-plan/1") ||
            CandidatePlanStageSha != StageRequestSha ||
            CandidatePlanDestination != CandidateDestination || CandidatePlanSource != SourceScene)
        {
            Error = TEXT("ArtFlow candidate plan is not bound to this exact stage request.");
        }
    }
    if (Error.IsEmpty())
    {
        SessionRunId = RunId;
        SessionSha256 = SessionSha;
    }

    FString SourceAfterSha;
    if (Error.IsEmpty() &&
        (!ArtFlowSceneBridge::HashFile(SessionSourceLevelPath, SourceAfterSha, Error) ||
        SourceAfterSha != SessionSourceLevelSha))
    {
        Error = TEXT("The source level changed during the read-only Scene Session handshake.");
    }
    if (Error.IsEmpty())
    {
        TSharedPtr<FJsonObject> HostReceipt = MakeShared<FJsonObject>();
        HostReceipt->SetStringField(
            TEXT("schema"),
            TEXT("artflow-unreal-scene-session-handshake-receipt/1"));
        HostReceipt->SetBoolField(TEXT("success"), true);
        HostReceipt->SetStringField(TEXT("endpoint_origin"), SessionEndpointOrigin);
        HostReceipt->SetStringField(TEXT("archive_sha256"), SessionArchiveSha);
        HostReceipt->SetStringField(TEXT("source_scene"), SessionSourceScene);
        HostReceipt->SetStringField(TEXT("source_level_sha256_before"), SessionSourceLevelSha);
        HostReceipt->SetStringField(TEXT("source_level_sha256_after"), SourceAfterSha);
        HostReceipt->SetBoolField(TEXT("source_level_unchanged"), true);
        HostReceipt->SetStringField(TEXT("received_at"), FDateTime::UtcNow().ToIso8601());
        HostReceipt->SetObjectField(TEXT("artflow_receipt"), BackendReceipt);
        FString ReceiptText;
        FJsonSerializer::Serialize(
            HostReceipt.ToSharedRef(),
            TJsonWriterFactory<>::Create(&ReceiptText));
        const FString ReceiptRoot =
            FPaths::Combine(ArtFlowSceneBridge::GetBridgeRoot(), TEXT("SceneSessions"));
        IFileManager::Get().MakeDirectory(*ReceiptRoot, true);
        ReceiptPath = FPaths::Combine(ReceiptRoot, HandshakeId + TEXT(".json"));
        if (!FFileHelper::SaveStringToFile(
            ReceiptText,
            *ReceiptPath,
            FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
        {
            Error = TEXT("The verified ArtFlow handshake receipt could not be saved.");
            ReceiptPath.Reset();
        }
    }

    if (Error.IsEmpty() && FParse::Param(FCommandLine::Get(), TEXT("ArtFlowExecuteSessionCandidate")))
    {
        UPCGComponent* CandidatePCG = nullptr;
        if (CandidatePlan == nullptr || !ArtFlowSceneBridge::StartSessionCandidateExecution(
            **CandidatePlan,
            CandidatePCG,
            bSessionCandidateReconciled,
            SessionCandidatePackage,
            SessionCandidatePlanId,
            SessionCandidatePlanSha,
            SessionCandidateStageRequestSha,
            SessionSourceLevelSha,
            SessionCandidateProtectedHash,
            Error))
        {
            if (Error.IsEmpty())
            {
                Error = TEXT("ArtFlow did not return an executable candidate plan.");
            }
        }
        else
        {
            SessionCandidatePCGComponent = CandidatePCG;
            bSessionCandidatePending = true;
            UE_LOG(
                LogArtFlowSceneBridge,
                Display,
                TEXT("ARTFLOW_SESSION_CANDIDATE_SUBMITTED plan=%s candidate=%s reconciled=%s"),
                *SessionCandidatePlanId,
                *SessionCandidatePackage,
                bSessionCandidateReconciled ? TEXT("true") : TEXT("false"));
        }
    }
    const bool bSuccess = Error.IsEmpty();
    UE_LOG(
        LogArtFlowSceneBridge,
        Display,
        TEXT("ARTFLOW_SESSION_HANDSHAKE_RESULT success=%s action=%s receipt=%s source_unchanged=%s error=%s"),
        bSuccess ? TEXT("true") : TEXT("false"),
        *SessionActionId,
        *ReceiptPath,
        bSuccess ? TEXT("true") : TEXT("unverified"),
        *Error);
    if (bSessionHandshakeAutomation)
    {
        if (!bSessionCandidatePending)
        {
            ArtFlowSceneBridge::WriteAutomationResult(bSuccess, ReceiptPath, Error);
            FPlatformMisc::RequestExit(false);
        }
    }
    else
    {
        if (bSuccess)
        {
            FNotificationInfo Info(FText::Format(
                LOCTEXT("SessionStartSuccess", "ArtFlow 场景任务已建立\n候选 {0} · 源关卡哈希未改变"),
                FText::FromString(FPaths::GetCleanFilename(CandidateDestination))));
            Info.bFireAndForget = true;
            Info.bUseLargeFont = false;
            Info.ExpireDuration = 30.0f;
            const TSharedPtr<SNotificationItem> Notification =
                FSlateNotificationManager::Get().AddNotification(Info);
            if (Notification.IsValid())
            {
                Notification->SetCompletionState(SNotificationItem::CS_Success);
            }
        }
        else
        {
            FMessageDialog::Open(
                EAppMsgType::Ok,
                FText::Format(
                    LOCTEXT("SessionHandshakeFailure", "ArtFlow 场景任务握手失败：\n{0}\n\n当前关卡未发生修改。"),
                    FText::FromString(Error)));
        }
    }
}

bool FArtFlowSceneBridgeModule::BeginSceneCandidateWorkDiscovery(
    const bool bAutomation,
    FString& OutError)
{
    if (bSceneCandidateWorkRequestPending || bSessionCandidatePending)
    {
        OutError = TEXT("An ArtFlow candidate work request is already active.");
        return false;
    }
    if (SessionRunId.IsEmpty() || !ArtFlowSceneBridge::IsSha256(SessionSha256) ||
        SessionEndpointOrigin.IsEmpty())
    {
        OutError = TEXT("Candidate work requires the current ArtFlow Run, Session and localhost endpoint.");
        return false;
    }
    SceneCandidateWorkerId = FString::Printf(
        TEXT("ue-editor-%u"), FPlatformProcess::GetCurrentProcessId());
    bSceneCandidateWorkAutomation = bAutomation;
    const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> HttpRequest =
        FHttpModule::Get().CreateRequest();
    HttpRequest->SetURL(
        SessionEndpointOrigin + TEXT("/api/agent/runs/") + SessionRunId);
    HttpRequest->SetVerb(TEXT("GET"));
    HttpRequest->SetTimeout(20.0f);
    HttpRequest->OnProcessRequestComplete().BindRaw(
        this, &FArtFlowSceneBridgeModule::HandleSceneCandidateWorkDiscovery);
    bSceneCandidateWorkRequestPending = true;
    if (!HttpRequest->ProcessRequest())
    {
        bSceneCandidateWorkRequestPending = false;
        OutError = TEXT("The current ArtFlow candidate work could not be requested.");
        return false;
    }
    return true;
}

void FArtFlowSceneBridgeModule::HandleSceneCandidateWorkDiscovery(
    FHttpRequestPtr Request,
    FHttpResponsePtr Response,
    const bool bConnectedSuccessfully)
{
    static_cast<void>(Request);
    bSceneCandidateWorkRequestPending = false;
    FString Error;
    TSharedPtr<FJsonObject> Projection;
    const int32 ResponseCode = Response.IsValid() ? Response->GetResponseCode() : 0;
    if (!bConnectedSuccessfully || !Response.IsValid() || ResponseCode != 200 ||
        !FJsonSerializer::Deserialize(
            TJsonReaderFactory<>::Create(Response.IsValid() ? Response->GetContentAsString() : TEXT("")),
            Projection) || !Projection.IsValid())
    {
        Error = TEXT("ArtFlow did not return the current candidate work projection.");
    }
    const TSharedPtr<FJsonObject>* Work = nullptr;
    const TSharedPtr<FJsonObject>* Definition = nullptr;
    FString Schema;
    FString RunId;
    FString Status;
    FString SessionSha;
    if (Error.IsEmpty() &&
        (!Projection->TryGetStringField(TEXT("schema_id"), Schema) ||
        !Projection->TryGetStringField(TEXT("run_id"), RunId) ||
        !Projection->TryGetObjectField(TEXT("scene_candidate_work"), Work) || Work == nullptr ||
        !(*Work)->TryGetStringField(TEXT("status"), Status) ||
        !(*Work)->TryGetObjectField(TEXT("definition"), Definition) || Definition == nullptr ||
        !(*Definition)->TryGetStringField(TEXT("work_sha256"), SceneCandidateWorkSha) ||
        !(*Definition)->TryGetStringField(TEXT("session_sha256"), SessionSha) ||
        Schema != TEXT("agent-run-projection/1") || RunId != SessionRunId ||
        SessionSha != SessionSha256 || Status != TEXT("queued") ||
        !ArtFlowSceneBridge::IsSha256(SceneCandidateWorkSha)))
    {
        Error = TEXT("The current Scene Session has no matching queued Unreal candidate work.");
    }
    if (Error.IsEmpty())
    {
        BeginSceneCandidateWorkClaim(Error);
    }
    if (!Error.IsEmpty())
    {
        UE_LOG(LogArtFlowSceneBridge, Error, TEXT("ARTFLOW_CANDIDATE_WORK_DISCOVERY_FAILED error=%s"), *Error);
        if (bSceneCandidateWorkAutomation)
        {
            ArtFlowSceneBridge::WriteAutomationResult(false, TEXT(""), Error);
            FPlatformMisc::RequestExit(false);
        }
        else
        {
            FMessageDialog::Open(EAppMsgType::Ok, FText::FromString(TEXT("ArtFlow 候选无法领取：\n") + Error));
        }
    }
}

bool FArtFlowSceneBridgeModule::BeginSceneCandidateWorkClaim(FString& OutError)
{
    TSharedPtr<FJsonObject> Payload = MakeShared<FJsonObject>();
    Payload->SetStringField(TEXT("schema_id"), TEXT("artflow-scene-candidate-claim/1"));
    Payload->SetStringField(TEXT("work_sha256"), SceneCandidateWorkSha);
    Payload->SetStringField(TEXT("session_sha256"), SessionSha256);
    Payload->SetStringField(TEXT("worker_id"), SceneCandidateWorkerId);
    FString Body;
    FJsonSerializer::Serialize(Payload.ToSharedRef(), TJsonWriterFactory<>::Create(&Body));
    const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> HttpRequest =
        FHttpModule::Get().CreateRequest();
    HttpRequest->SetURL(
        SessionEndpointOrigin + TEXT("/api/agent/runs/") + SessionRunId +
        TEXT("/scene-candidate-work/claim"));
    HttpRequest->SetVerb(TEXT("POST"));
    HttpRequest->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    HttpRequest->SetContentAsString(Body);
    HttpRequest->SetTimeout(20.0f);
    HttpRequest->OnProcessRequestComplete().BindRaw(
        this, &FArtFlowSceneBridgeModule::HandleSceneCandidateWorkClaim);
    bSceneCandidateWorkRequestPending = true;
    if (!HttpRequest->ProcessRequest())
    {
        bSceneCandidateWorkRequestPending = false;
        OutError = TEXT("The candidate work claim could not be submitted.");
        return false;
    }
    return true;
}

void FArtFlowSceneBridgeModule::HandleSceneCandidateWorkClaim(
    FHttpRequestPtr Request,
    FHttpResponsePtr Response,
    const bool bConnectedSuccessfully)
{
    static_cast<void>(Request);
    bSceneCandidateWorkRequestPending = false;
    FString Error;
    TSharedPtr<FJsonObject> Projection;
    const int32 ResponseCode = Response.IsValid() ? Response->GetResponseCode() : 0;
    if (!bConnectedSuccessfully || !Response.IsValid() || ResponseCode != 200 ||
        !FJsonSerializer::Deserialize(
            TJsonReaderFactory<>::Create(Response.IsValid() ? Response->GetContentAsString() : TEXT("")),
            Projection) || !Projection.IsValid())
    {
        Error = FString::Printf(TEXT("ArtFlow rejected the candidate work claim (HTTP %d)."), ResponseCode);
    }
    const TSharedPtr<FJsonObject>* Work = nullptr;
    const TSharedPtr<FJsonObject>* Definition = nullptr;
    const TSharedPtr<FJsonObject>* CandidatePlan = nullptr;
    FString Status;
    FString WorkerId;
    FString WorkSha;
    if (Error.IsEmpty() &&
        (!Projection->TryGetObjectField(TEXT("scene_candidate_work"), Work) || Work == nullptr ||
        !(*Work)->TryGetStringField(TEXT("status"), Status) ||
        !(*Work)->TryGetStringField(TEXT("worker_id"), WorkerId) ||
        !(*Work)->TryGetObjectField(TEXT("definition"), Definition) || Definition == nullptr ||
        !(*Definition)->TryGetStringField(TEXT("work_sha256"), WorkSha) ||
        !(*Definition)->TryGetObjectField(TEXT("candidate_plan"), CandidatePlan) || CandidatePlan == nullptr ||
        Status != TEXT("claimed") || WorkerId != SceneCandidateWorkerId ||
        WorkSha != SceneCandidateWorkSha))
    {
        Error = TEXT("The claimed candidate work identity does not match this Unreal editor.");
    }
    if (Error.IsEmpty())
    {
        PendingSceneCandidatePlan = *CandidatePlan;
        BeginSceneCandidateWorkProgress(
            TEXT("executing"), TEXT(""), TEXT("Unreal 正在生成隔离候选关卡"), Error);
    }
    if (!Error.IsEmpty())
    {
        UE_LOG(LogArtFlowSceneBridge, Error, TEXT("ARTFLOW_CANDIDATE_WORK_CLAIM_FAILED error=%s"), *Error);
        if (bSceneCandidateWorkAutomation)
        {
            ArtFlowSceneBridge::WriteAutomationResult(false, TEXT(""), Error);
            FPlatformMisc::RequestExit(false);
        }
        else
        {
            FMessageDialog::Open(EAppMsgType::Ok, FText::FromString(TEXT("ArtFlow 候选领取失败：\n") + Error));
        }
    }
}

bool FArtFlowSceneBridgeModule::BeginSceneCandidateWorkProgress(
    const FString& Status,
    const FString& OutcomeSha256,
    const FString& Message,
    FString& OutError)
{
    if (bSceneCandidateWorkRequestPending)
    {
        OutError = TEXT("Another ArtFlow candidate work request is pending.");
        return false;
    }
    TSharedPtr<FJsonObject> Payload = MakeShared<FJsonObject>();
    Payload->SetStringField(TEXT("schema_id"), TEXT("artflow-scene-candidate-progress/1"));
    Payload->SetStringField(TEXT("work_sha256"), SceneCandidateWorkSha);
    Payload->SetStringField(TEXT("worker_id"), SceneCandidateWorkerId);
    Payload->SetStringField(TEXT("status"), Status);
    Payload->SetStringField(TEXT("action_id"), TEXT("ue-") + Status + TEXT("-") + SceneCandidateWorkSha.Left(16));
    if (!OutcomeSha256.IsEmpty()) Payload->SetStringField(TEXT("outcome_sha256"), OutcomeSha256);
    if (!Message.IsEmpty()) Payload->SetStringField(TEXT("message"), Message);
    FString Body;
    FJsonSerializer::Serialize(Payload.ToSharedRef(), TJsonWriterFactory<>::Create(&Body));
    const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> HttpRequest = FHttpModule::Get().CreateRequest();
    HttpRequest->SetURL(
        SessionEndpointOrigin + TEXT("/api/agent/runs/") + SessionRunId +
        TEXT("/scene-candidate-work/progress"));
    HttpRequest->SetVerb(TEXT("POST"));
    HttpRequest->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    HttpRequest->SetContentAsString(Body);
    HttpRequest->SetTimeout(20.0f);
    HttpRequest->OnProcessRequestComplete().BindRaw(
        this, &FArtFlowSceneBridgeModule::HandleSceneCandidateWorkProgress);
    SceneCandidateProgressStatus = Status;
    bSceneCandidateWorkRequestPending = true;
    if (!HttpRequest->ProcessRequest())
    {
        bSceneCandidateWorkRequestPending = false;
        OutError = TEXT("Candidate work progress could not be submitted.");
        return false;
    }
    return true;
}

void FArtFlowSceneBridgeModule::HandleSceneCandidateWorkProgress(
    FHttpRequestPtr Request,
    FHttpResponsePtr Response,
    const bool bConnectedSuccessfully)
{
    static_cast<void>(Request);
    bSceneCandidateWorkRequestPending = false;
    FString Error;
    TSharedPtr<FJsonObject> Projection;
    const int32 ResponseCode = Response.IsValid() ? Response->GetResponseCode() : 0;
    if (!bConnectedSuccessfully || !Response.IsValid() || ResponseCode != 200 ||
        !FJsonSerializer::Deserialize(
            TJsonReaderFactory<>::Create(Response.IsValid() ? Response->GetContentAsString() : TEXT("")),
            Projection) || !Projection.IsValid())
    {
        Error = FString::Printf(TEXT("ArtFlow rejected candidate progress (HTTP %d)."), ResponseCode);
    }
    const TSharedPtr<FJsonObject>* Work = nullptr;
    FString Status;
    if (Error.IsEmpty() &&
        (!Projection->TryGetObjectField(TEXT("scene_candidate_work"), Work) || Work == nullptr ||
        !(*Work)->TryGetStringField(TEXT("status"), Status) ||
        Status != SceneCandidateProgressStatus))
    {
        Error = TEXT("Candidate progress response does not match the submitted state.");
    }
    if (Error.IsEmpty() && SceneCandidateProgressStatus == TEXT("executing"))
    {
        UPCGComponent* CandidatePCG = nullptr;
        if (!PendingSceneCandidatePlan.IsValid() ||
            !ArtFlowSceneBridge::StartSessionCandidateExecution(
                *PendingSceneCandidatePlan,
                CandidatePCG,
                bSessionCandidateReconciled,
                SessionCandidatePackage,
                SessionCandidatePlanId,
                SessionCandidatePlanSha,
                SessionCandidateStageRequestSha,
                SessionSourceLevelSha,
                SessionCandidateProtectedHash,
                Error))
        {
            if (Error.IsEmpty()) Error = TEXT("The claimed work contains no executable candidate plan.");
        }
        else
        {
            PendingSceneCandidatePlan.Reset();
            SessionCandidatePCGComponent = CandidatePCG;
            bSessionCandidatePending = true;
            if (!AutomationTickHandle.IsValid())
            {
                AutomationTickHandle = FTSTicker::GetCoreTicker().AddTicker(
                    FTickerDelegate::CreateRaw(this, &FArtFlowSceneBridgeModule::TickAutomation), 1.0f);
            }
            UE_LOG(
                LogArtFlowSceneBridge,
                Display,
                TEXT("ARTFLOW_CANDIDATE_WORK_EXECUTING work=%s plan=%s worker=%s"),
                *SceneCandidateWorkSha, *SessionCandidatePlanId, *SceneCandidateWorkerId);
            return;
        }
    }
    if (Error.IsEmpty() && SceneCandidateProgressStatus == TEXT("reconciling"))
    {
        BeginSceneCandidateWorkProgress(
            TEXT("succeeded"),
            SceneCandidateFinalOutcomeSha,
            TEXT("候选关卡已完成并通过 Unreal 宿主复检"),
            Error);
        if (Error.IsEmpty()) return;
    }
    if (Error.IsEmpty() &&
        (SceneCandidateProgressStatus == TEXT("succeeded") || SceneCandidateProgressStatus == TEXT("failed")))
    {
        const bool bSucceeded = SceneCandidateProgressStatus == TEXT("succeeded");
        UE_LOG(
            LogArtFlowSceneBridge,
            Display,
            TEXT("ARTFLOW_CANDIDATE_WORK_RESULT success=%s work=%s receipt=%s error=%s"),
            bSucceeded ? TEXT("true") : TEXT("false"),
            *SceneCandidateWorkSha,
            *SceneCandidateFinalReceiptPath,
            *SceneCandidateFinalError);
        if (bSceneCandidateWorkAutomation)
        {
            ArtFlowSceneBridge::WriteAutomationResult(
                bSucceeded, SceneCandidateFinalReceiptPath, SceneCandidateFinalError);
            FPlatformMisc::RequestExit(false);
        }
        else
        {
            FNotificationInfo Info(FText::FromString(
                bSucceeded
                    ? TEXT("ArtFlow 候选关卡已生成并同步到场景变更谱")
                    : TEXT("ArtFlow 候选执行停止；源关卡未修改")));
            Info.bFireAndForget = true;
            Info.ExpireDuration = 12.0f;
            const TSharedPtr<SNotificationItem> Notification =
                FSlateNotificationManager::Get().AddNotification(Info);
            if (Notification.IsValid())
            {
                Notification->SetCompletionState(
                    bSucceeded ? SNotificationItem::CS_Success : SNotificationItem::CS_Fail);
            }
        }
        return;
    }
    if (!Error.IsEmpty() && SceneCandidateProgressStatus == TEXT("executing"))
    {
        SceneCandidateFinalReceiptPath.Reset();
        SceneCandidateFinalError = Error;
        FString SyncError;
        if (BeginSceneCandidateWorkProgress(
            TEXT("failed"), TEXT(""), Error.Left(500), SyncError))
        {
            return;
        }
        Error += TEXT(" Final failure sync also failed: ") + SyncError;
    }
    if (!Error.IsEmpty())
    {
        UE_LOG(LogArtFlowSceneBridge, Error, TEXT("ARTFLOW_CANDIDATE_WORK_PROGRESS_FAILED error=%s"), *Error);
        if (bSceneCandidateWorkAutomation)
        {
            ArtFlowSceneBridge::WriteAutomationResult(false, SceneCandidateFinalReceiptPath, Error);
            FPlatformMisc::RequestExit(false);
        }
    }
}

bool FArtFlowSceneBridgeModule::BeginSceneLifecycleCallback(
    const FString& Transition,
    const FString& ArtifactSha256,
    const FString& ActionId,
    const bool bAutomation,
    FString& OutError)
{
    if (bSceneLifecycleCallbackPending)
    {
        OutError = TEXT("An ArtFlow scene lifecycle callback is already pending.");
        return false;
    }
    const TSet<FString> AllowedTransitions = {
        TEXT("evaluation"), TEXT("adoption"), TEXT("publication"), TEXT("review")};
    const FString NormalizedTransition = Transition.TrimStartAndEnd().ToLower();
    if (!AllowedTransitions.Contains(NormalizedTransition))
    {
        OutError = TEXT("Lifecycle transition is not registered by ArtFlow.");
        return false;
    }
    if (!ArtFlowSceneBridge::IsSha256(ArtifactSha256) ||
        !ArtFlowSceneBridge::IsSha256(SessionSha256))
    {
        OutError = TEXT("Lifecycle callback requires exact lowercase SHA-256 identities.");
        return false;
    }
    if (SessionRunId.IsEmpty() || SessionRunId.Len() > 120 ||
        ActionId.Len() < 3 || ActionId.Len() > 120)
    {
        OutError = TEXT("Lifecycle callback run or action identity is invalid.");
        return false;
    }
    for (const TCHAR Character : ActionId)
    {
        if (!FChar::IsAlnum(Character) && Character != TEXT('.') &&
            Character != TEXT('_') && Character != TEXT('-'))
        {
            OutError = TEXT("Lifecycle callback action identity contains unsupported characters.");
            return false;
        }
    }
    ArtFlowSceneBridge::FCaptureRequest CaptureRequest;
    if (!ArtFlowSceneBridge::LoadCaptureRequest(CaptureRequest, OutError) ||
        !ArtFlowSceneBridge::NormalizeLoopbackOrigin(
            CaptureRequest.ArtFlowEndpoint,
            SessionEndpointOrigin,
            OutError))
    {
        return false;
    }

    TSharedPtr<FJsonObject> Payload = MakeShared<FJsonObject>();
    Payload->SetStringField(TEXT("schema_id"), TEXT("artflow-scene-variant-callback/1"));
    Payload->SetStringField(TEXT("transition"), NormalizedTransition);
    Payload->SetStringField(TEXT("session_sha256"), SessionSha256);
    Payload->SetStringField(TEXT("artifact_sha256"), ArtifactSha256);
    Payload->SetStringField(TEXT("action_id"), ActionId);
    FString PayloadText;
    FJsonSerializer::Serialize(
        Payload.ToSharedRef(),
        TJsonWriterFactory<>::Create(&PayloadText));

    SceneLifecycleTransition = NormalizedTransition;
    SceneLifecycleArtifactSha256 = ArtifactSha256;
    SceneLifecycleActionId = ActionId;
    bSceneLifecycleCallbackAutomation = bAutomation;
    const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> HttpRequest =
        FHttpModule::Get().CreateRequest();
    HttpRequest->SetURL(
        SessionEndpointOrigin + TEXT("/api/agent/runs/") + SessionRunId +
        TEXT("/scene-variant-lifecycle/callback"));
    HttpRequest->SetVerb(TEXT("POST"));
    HttpRequest->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    HttpRequest->SetContentAsString(PayloadText);
    HttpRequest->SetTimeout(30.0f);
    HttpRequest->OnProcessRequestComplete().BindRaw(
        this,
        &FArtFlowSceneBridgeModule::HandleSceneLifecycleCallback);
    bSceneLifecycleCallbackPending = true;
    if (!HttpRequest->ProcessRequest())
    {
        bSceneLifecycleCallbackPending = false;
        OutError = TEXT("The localhost lifecycle callback could not be submitted.");
        return false;
    }
    UE_LOG(
        LogArtFlowSceneBridge,
        Display,
        TEXT("ARTFLOW_LIFECYCLE_CALLBACK_SUBMITTED transition=%s artifact=%s action=%s run=%s"),
        *SceneLifecycleTransition,
        *SceneLifecycleArtifactSha256,
        *SceneLifecycleActionId,
        *SessionRunId);
    return true;
}

void FArtFlowSceneBridgeModule::HandleSceneLifecycleCallback(
    FHttpRequestPtr Request,
    FHttpResponsePtr Response,
    const bool bConnectedSuccessfully)
{
    static_cast<void>(Request);
    bSceneLifecycleCallbackPending = false;
    FString Error;
    FString ReceiptPath;
    TSharedPtr<FJsonObject> Projection;
    const int32 ResponseCode = Response.IsValid() ? Response->GetResponseCode() : 0;
    if (!bConnectedSuccessfully || !Response.IsValid())
    {
        Error = TEXT("The localhost ArtFlow runtime did not return a lifecycle response.");
    }
    else if (ResponseCode != 200)
    {
        Error = FString::Printf(
            TEXT("ArtFlow rejected the lifecycle callback (HTTP %d): %s"),
            ResponseCode,
            *Response->GetContentAsString().Left(800));
    }
    else if (!FJsonSerializer::Deserialize(
        TJsonReaderFactory<>::Create(Response->GetContentAsString()),
        Projection) || !Projection.IsValid())
    {
        Error = TEXT("ArtFlow returned invalid lifecycle projection JSON.");
    }

    FString Schema;
    FString RunId;
    const TSharedPtr<FJsonObject>* Session = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* Timeline = nullptr;
    if (Error.IsEmpty() &&
        (!Projection->TryGetStringField(TEXT("schema_id"), Schema) ||
        !Projection->TryGetStringField(TEXT("run_id"), RunId) ||
        !Projection->TryGetObjectField(TEXT("scene_session"), Session) ||
        Session == nullptr ||
        !Projection->TryGetArrayField(TEXT("timeline"), Timeline) ||
        Timeline == nullptr || Timeline->IsEmpty()))
    {
        Error = TEXT("ArtFlow lifecycle projection is missing required typed fields.");
    }
    FString ReturnedSessionSha;
    if (Error.IsEmpty())
    {
        (*Session)->TryGetStringField(TEXT("session_sha256"), ReturnedSessionSha);
    }
    FString ExpectedEventType;
    if (SceneLifecycleTransition == TEXT("evaluation")) ExpectedEventType = TEXT("scene_candidate_evaluated");
    else if (SceneLifecycleTransition == TEXT("adoption")) ExpectedEventType = TEXT("scene_candidate_adopted");
    else if (SceneLifecycleTransition == TEXT("publication")) ExpectedEventType = TEXT("scene_variant_published");
    else ExpectedEventType = TEXT("scene_variant_reviewed");
    bool bExpectedEventFound = false;
    if (Error.IsEmpty())
    {
        for (const TSharedPtr<FJsonValue>& TimelineValue : *Timeline)
        {
            const TSharedPtr<FJsonObject>* Event = nullptr;
            FString EventType;
            if (TimelineValue.IsValid() && TimelineValue->TryGetObject(Event) &&
                Event != nullptr && (*Event)->TryGetStringField(TEXT("event_type"), EventType) &&
                EventType == ExpectedEventType)
            {
                bExpectedEventFound = true;
                break;
            }
        }
    }
    if (Error.IsEmpty() &&
        (Schema != TEXT("agent-run-projection/1") || RunId != SessionRunId ||
        ReturnedSessionSha != SessionSha256 || !bExpectedEventFound))
    {
        Error = TEXT("Lifecycle response does not match the current Run, Session or transition.");
    }

    if (Error.IsEmpty())
    {
        TSharedPtr<FJsonObject> HostReceipt = MakeShared<FJsonObject>();
        HostReceipt->SetStringField(
            TEXT("schema"), TEXT("artflow-unreal-lifecycle-callback-receipt/1"));
        HostReceipt->SetBoolField(TEXT("success"), true);
        HostReceipt->SetStringField(TEXT("endpoint_origin"), SessionEndpointOrigin);
        HostReceipt->SetStringField(TEXT("run_id"), SessionRunId);
        HostReceipt->SetStringField(TEXT("session_sha256"), SessionSha256);
        HostReceipt->SetStringField(TEXT("transition"), SceneLifecycleTransition);
        HostReceipt->SetStringField(TEXT("artifact_sha256"), SceneLifecycleArtifactSha256);
        HostReceipt->SetStringField(TEXT("action_id"), SceneLifecycleActionId);
        HostReceipt->SetStringField(TEXT("event_type"), ExpectedEventType);
        HostReceipt->SetStringField(TEXT("received_at"), FDateTime::UtcNow().ToIso8601());
        FString ReceiptText;
        FJsonSerializer::Serialize(
            HostReceipt.ToSharedRef(),
            TJsonWriterFactory<>::Create(&ReceiptText));
        const FString ReceiptRoot =
            FPaths::Combine(ArtFlowSceneBridge::GetBridgeRoot(), TEXT("SceneSessions"));
        IFileManager::Get().MakeDirectory(*ReceiptRoot, true);
        ReceiptPath = FPaths::Combine(
            ReceiptRoot,
            TEXT("lifecycle-") + SceneLifecycleActionId + TEXT(".json"));
        if (!FFileHelper::SaveStringToFile(
            ReceiptText,
            *ReceiptPath,
            FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
        {
            Error = TEXT("The verified lifecycle callback receipt could not be saved.");
            ReceiptPath.Reset();
        }
    }

    const bool bSuccess = Error.IsEmpty();
    UE_LOG(
        LogArtFlowSceneBridge,
        Display,
        TEXT("ARTFLOW_LIFECYCLE_CALLBACK_RESULT success=%s transition=%s artifact=%s receipt=%s error=%s"),
        bSuccess ? TEXT("true") : TEXT("false"),
        *SceneLifecycleTransition,
        *SceneLifecycleArtifactSha256,
        *ReceiptPath,
        *Error);
    if (bSceneLifecycleCallbackAutomation)
    {
        ArtFlowSceneBridge::WriteAutomationResult(bSuccess, ReceiptPath, Error);
        FPlatformMisc::RequestExit(false);
    }
    else if (bSuccess)
    {
        FNotificationInfo Info(FText::Format(
            LOCTEXT("LifecycleCallbackSuccess", "ArtFlow 场景状态已同步\n{0} 已进入当前 Scene Session"),
            FText::FromString(SceneLifecycleTransition)));
        Info.bFireAndForget = true;
        Info.bUseLargeFont = false;
        Info.ExpireDuration = 12.0f;
        const TSharedPtr<SNotificationItem> Notification =
            FSlateNotificationManager::Get().AddNotification(Info);
        if (Notification.IsValid())
        {
            Notification->SetCompletionState(SNotificationItem::CS_Success);
        }
    }
    else
    {
        FMessageDialog::Open(
            EAppMsgType::Ok,
            FText::Format(
                LOCTEXT("LifecycleCallbackFailure", "ArtFlow 场景状态同步失败：\n{0}"),
                FText::FromString(Error)));
    }
}

void FArtFlowSceneBridgeModule::ReviewLastExport() const
{
    const FString Message = LastExportPath.IsEmpty()
        ? TEXT("本次编辑器会话尚未导出 Scene Package。")
        : FString::Printf(TEXT("最近完成的 Scene Package：\n%s"), *LastExportPath);
    FMessageDialog::Open(EAppMsgType::Ok, FText::FromString(Message));
}

bool FArtFlowSceneBridgeModule::TickAutomation(float DeltaTime)
{
    if (bSessionCandidatePending)
    {
        if (SessionCandidatePCGComponent.IsValid() &&
            SessionCandidatePCGComponent->IsGenerating())
        {
            return true;
        }
        bSessionCandidatePending = false;
        FString Error;
        FString ReceiptPath;
        const bool bSuccess = ArtFlowSceneBridge::FinalizeSessionCandidateExecution(
            bSessionCandidateReconciled,
            SessionCandidatePackage,
            SessionCandidatePlanId,
            SessionCandidatePlanSha,
            SessionCandidateStageRequestSha,
            SessionSourceLevelSha,
            SessionCandidateProtectedHash,
            ReceiptPath,
            Error);
        if (!SceneCandidateWorkSha.IsEmpty())
        {
            FString OutcomeSha;
            bool bWorkSuccess = bSuccess;
            if (bWorkSuccess && !ArtFlowSceneBridge::HashFile(ReceiptPath, OutcomeSha, Error))
            {
                bWorkSuccess = false;
            }
            SceneCandidateFinalReceiptPath = ReceiptPath;
            SceneCandidateFinalError = Error;
            FString ProgressError;
            SceneCandidateFinalOutcomeSha = bWorkSuccess ? OutcomeSha : TEXT("");
            const FString ProgressStatus = bWorkSuccess ? TEXT("reconciling") : TEXT("failed");
            const FString ProgressMessage = bWorkSuccess
                ? TEXT("候选关卡已生成，正在核对宿主回执与内容身份")
                : (Error.IsEmpty() ? TEXT("候选执行失败，源关卡未修改") : Error.Left(500));
            if (!BeginSceneCandidateWorkProgress(
                ProgressStatus,
                bWorkSuccess ? OutcomeSha : TEXT(""),
                ProgressMessage,
                ProgressError))
            {
                UE_LOG(
                    LogArtFlowSceneBridge,
                    Error,
                    TEXT("ARTFLOW_CANDIDATE_WORK_FINAL_SYNC_FAILED error=%s"),
                    *ProgressError);
                if (bSceneCandidateWorkAutomation)
                {
                    ArtFlowSceneBridge::WriteAutomationResult(false, ReceiptPath, ProgressError);
                    FPlatformMisc::RequestExit(false);
                }
            }
            AutomationTickHandle.Reset();
            return false;
        }
        ArtFlowSceneBridge::WriteAutomationResult(bSuccess, ReceiptPath, Error);
        UE_LOG(
            LogArtFlowSceneBridge,
            Display,
            TEXT("ARTFLOW_SESSION_CANDIDATE_RESULT success=%s receipt=%s reconciled=%s error=%s"),
            bSuccess ? TEXT("true") : TEXT("false"),
            *ReceiptPath,
            bSessionCandidateReconciled ? TEXT("true") : TEXT("false"),
            *Error);
        FPlatformMisc::RequestExit(false);
        return false;
    }
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
    if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowClaimCandidateWork")))
    {
        FString Endpoint;
        if (!FParse::Value(FCommandLine::Get(), TEXT("ArtFlowCandidateRun="), SessionRunId) ||
            !FParse::Value(FCommandLine::Get(), TEXT("ArtFlowCandidateSession="), SessionSha256) ||
            !FParse::Value(FCommandLine::Get(), TEXT("ArtFlowEndpoint="), Endpoint) ||
            !ArtFlowSceneBridge::NormalizeLoopbackOrigin(Endpoint, SessionEndpointOrigin, Error))
        {
            if (Error.IsEmpty())
            {
                Error = TEXT("Candidate work automation requires Run, Session and localhost endpoint identities.");
            }
        }
        else if (ArtFlowSceneBridge::PrepareExistingAutomationScene(false, Error) &&
            BeginSceneCandidateWorkDiscovery(true, Error))
        {
            return true;
        }
    }
    else if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowLifecycleCallback")))
    {
        FString Transition;
        FString ArtifactSha256;
        FString ActionId;
        if (!FParse::Value(FCommandLine::Get(), TEXT("ArtFlowLifecycleRun="), SessionRunId) ||
            !FParse::Value(FCommandLine::Get(), TEXT("ArtFlowLifecycleSession="), SessionSha256) ||
            !FParse::Value(FCommandLine::Get(), TEXT("ArtFlowLifecycleTransition="), Transition) ||
            !FParse::Value(FCommandLine::Get(), TEXT("ArtFlowLifecycleArtifact="), ArtifactSha256) ||
            !FParse::Value(FCommandLine::Get(), TEXT("ArtFlowLifecycleAction="), ActionId))
        {
            Error = TEXT("Lifecycle callback automation requires Run, Session, transition, artifact and action identities.");
        }
        else if (BeginSceneLifecycleCallback(
            Transition,
            ArtifactSha256,
            ActionId,
            true,
            Error))
        {
            return true;
        }
    }
    else if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowPublishStage")) || FParse::Param(FCommandLine::Get(), TEXT("ArtFlowDiscardStage")))
    {
        const bool bPublish = FParse::Param(FCommandLine::Get(), TEXT("ArtFlowPublishStage"));
        bSuccess = ArtFlowSceneBridge::ExecuteStageDisposition(bPublish, ArchivePath, Error);
    }
    else if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowExecuteStage")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowCaptureStage")))
    {
        UPCGComponent* Component = nullptr;
        const bool bCaptureOnly = FParse::Param(FCommandLine::Get(), TEXT("ArtFlowCaptureStage"));
        bSuccess = ArtFlowSceneBridge::StartCandidateExecution(
            Component, bStageReconciled, StageSourceHash, StageProtectedHash, Error, !bCaptureOnly);
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
    else if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowReconcileSessionCandidate")))
    {
        FString ReceiptPath;
        FString ReceiptText;
        TSharedPtr<FJsonObject> HostReceipt;
        const TSharedPtr<FJsonObject>* ArtFlowReceipt = nullptr;
        const TSharedPtr<FJsonObject>* CandidatePlan = nullptr;
        if (!FParse::Value(FCommandLine::Get(), TEXT("ArtFlowCandidateReceipt="), ReceiptPath) ||
            !ArtFlowSceneBridge::IsPathInside(
                ReceiptPath,
                FPaths::Combine(ArtFlowSceneBridge::GetBridgeRoot(), TEXT("SceneSessions"))) ||
            FPaths::GetExtension(ReceiptPath).ToLower() != TEXT("json") ||
            !FFileHelper::LoadFileToString(ReceiptText, *ReceiptPath) ||
            !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ReceiptText), HostReceipt) ||
            !HostReceipt.IsValid() ||
            !HostReceipt->TryGetObjectField(TEXT("artflow_receipt"), ArtFlowReceipt) ||
            ArtFlowReceipt == nullptr ||
            !(*ArtFlowReceipt)->TryGetObjectField(TEXT("candidate_plan"), CandidatePlan) ||
            CandidatePlan == nullptr)
        {
            Error = TEXT("Candidate reconciliation requires a verified ArtFlow handshake receipt.");
        }
        else
        {
            UPCGComponent* CandidatePCG = nullptr;
            bSuccess = ArtFlowSceneBridge::StartSessionCandidateExecution(
                **CandidatePlan,
                CandidatePCG,
                bSessionCandidateReconciled,
                SessionCandidatePackage,
                SessionCandidatePlanId,
                SessionCandidatePlanSha,
                SessionCandidateStageRequestSha,
                SessionSourceLevelSha,
                SessionCandidateProtectedHash,
                Error);
            if (bSuccess)
            {
                SessionCandidatePCGComponent = CandidatePCG;
                bSessionCandidatePending = true;
                return true;
            }
        }
    }
    else if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowSessionHandshake")) ||
        FParse::Param(FCommandLine::Get(), TEXT("ArtFlowExecuteSessionCandidate")))
    {
        bSuccess = ArtFlowSceneBridge::PrepareExistingAutomationScene(false, Error) &&
            ArtFlowSceneBridge::ExportSelection(ArchivePath, Error);
        if (bSuccess)
        {
            LastExportPath = ArchivePath;
            const bool bKeepOpen =
                FParse::Param(FCommandLine::Get(), TEXT("ArtFlowKeepOpen"));
            if (BeginSceneSessionHandshake(ArchivePath, !bKeepOpen, Error))
            {
                return true;
            }
            bSuccess = false;
        }
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
