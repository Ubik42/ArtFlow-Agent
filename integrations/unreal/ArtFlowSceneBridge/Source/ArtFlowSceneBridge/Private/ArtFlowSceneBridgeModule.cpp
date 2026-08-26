#include "ArtFlowSceneBridgeModule.h"

#include "BufferVisualizationData.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Components/StaticMeshComponent.h"
#include "Editor.h"
#include "Editor/EditorEngine.h"
#include "Engine/DirectionalLight.h"
#include "Engine/Engine.h"
#include "Engine/Selection.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/TextureRenderTarget2D.h"
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
#include "Misc/ScopeExit.h"
#include "Misc/ScopedSlowTask.h"
#include "RenderingThread.h"
#include "ToolMenus.h"

#define LOCTEXT_NAMESPACE "ArtFlowSceneBridge"

DEFINE_LOG_CATEGORY_STATIC(LogArtFlowSceneBridge, Log, All);

namespace ArtFlowSceneBridge
{
constexpr int32 DefaultWidth = 640;
constexpr int32 DefaultHeight = 360;
constexpr float DefaultFarClip = 100000.0f;
const FName ProtectedTag(TEXT("ArtFlow.Protected"));
const FName EditableTag(TEXT("ArtFlow.Editable"));

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

bool WriteManifest(
    const FString& ManifestPath,
    const FString& PackageId,
    const FCaptureRequest& Request,
    const ACameraActor* Camera,
    const TArray<FPassFile>& Passes,
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

bool WriteAtomicArchive(const FString& FinalPath, const FString& ManifestPath, const TArray<FPassFile>& Passes, FString& OutError)
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
    if (!Step(LOCTEXT("ManifestPass", "Writing signed manifest")))
    {
        return false;
    }
    const FString ManifestPath = FPaths::Combine(StagingRoot, TEXT("scene-package.json"));
    if (!WriteManifest(ManifestPath, PackageId, Request, Camera, Passes, ProtectedActors, EditableActors, OutError))
    {
        return false;
    }
    if (!Step(LOCTEXT("ArchivePass", "Publishing atomic package")))
    {
        return false;
    }
    OutArchivePath = FPaths::Combine(GetExportRoot(), PackageId + TEXT(".zip"));
    return WriteAtomicArchive(OutArchivePath, ManifestPath, Passes, OutError);
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
    if (FParse::Param(FCommandLine::Get(), TEXT("ArtFlowCreateDemoAndExport")))
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
    if (bAutomationHandled || GEditor == nullptr || GEditor->GetEditorWorldContext().World() == nullptr)
    {
        return true;
    }
    bAutomationHandled = true;
    FString Error;
    FString ArchivePath;
    const bool bSuccess = ArtFlowSceneBridge::CreateAutomationScene(Error) && ArtFlowSceneBridge::ExportSelection(ArchivePath, Error);
    if (bSuccess)
    {
        LastExportPath = ArchivePath;
    }
    ArtFlowSceneBridge::WriteAutomationResult(bSuccess, ArchivePath, Error);
    UE_LOG(LogArtFlowSceneBridge, Display, TEXT("ARTFLOW_AUTOMATION_RESULT success=%s archive=%s error=%s"), bSuccess ? TEXT("true") : TEXT("false"), *ArchivePath, *Error);
    return false;
}

IMPLEMENT_MODULE(FArtFlowSceneBridgeModule, ArtFlowSceneBridge)

#undef LOCTEXT_NAMESPACE
