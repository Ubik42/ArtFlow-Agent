#pragma once

#include "Containers/Ticker.h"
#include "Interfaces/IHttpRequest.h"
#include "Modules/ModuleManager.h"

class UPCGComponent;
class FJsonObject;

class FArtFlowSceneBridgeModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

private:
    void RegisterMenus();
    void ExportSelectedScene();
    void StartSceneSession();
    void ExecuteCurrentCandidateWork();
    bool BeginSceneSessionHandshake(const FString& ArchivePath, bool bAutomation, FString& OutError);
    void HandleSceneSessionHandshake(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnectedSuccessfully);
    bool BeginSceneLifecycleCallback(
        const FString& Transition,
        const FString& ArtifactSha256,
        const FString& ActionId,
        bool bAutomation,
        FString& OutError);
    void HandleSceneLifecycleCallback(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnectedSuccessfully);
    bool BeginSceneCandidateWorkDiscovery(bool bAutomation, FString& OutError);
    void HandleSceneCandidateWorkDiscovery(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnectedSuccessfully);
    bool BeginSceneCandidateWorkClaim(FString& OutError);
    void HandleSceneCandidateWorkClaim(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnectedSuccessfully);
    bool BeginSceneCandidateWorkProgress(
        const FString& Status,
        const FString& OutcomeSha256,
        const FString& Message,
        FString& OutError);
    void HandleSceneCandidateWorkProgress(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnectedSuccessfully);
    void ReviewLastExport() const;
    bool TickAutomation(float DeltaTime);

    FTSTicker::FDelegateHandle AutomationTickHandle;
    bool bAutomationHandled = false;
    bool bStageGenerationPending = false;
    bool bSessionHandshakePending = false;
    bool bSessionHandshakeAutomation = false;
    bool bSceneLifecycleCallbackPending = false;
    bool bSceneLifecycleCallbackAutomation = false;
    bool bSceneCandidateWorkRequestPending = false;
    bool bSceneCandidateWorkAutomation = false;
    bool bSessionCandidatePending = false;
    bool bSessionCandidateReconciled = false;
    bool bStageReconciled = false;
    TWeakObjectPtr<UPCGComponent> StagePCGComponent;
    TWeakObjectPtr<UPCGComponent> SessionCandidatePCGComponent;
    FString StageSourceHash;
    FString StageProtectedHash;
    FString LastExportPath;
    FString SessionArchivePath;
    FString SessionArchiveSha;
    FString SessionSourceScene;
    FString SessionSourceLevelPath;
    FString SessionSourceLevelSha;
    FString SessionActionId;
    FString SessionRunId;
    FString SessionSha256;
    FString SessionEndpointOrigin;
    FString SceneLifecycleTransition;
    FString SceneLifecycleArtifactSha256;
    FString SceneLifecycleActionId;
    FString SceneCandidateWorkSha;
    FString SceneCandidateWorkerId;
    FString SceneCandidateProgressStatus;
    FString SceneCandidateFinalReceiptPath;
    FString SceneCandidateFinalOutcomeSha;
    FString SceneCandidateFinalError;
    TSharedPtr<FJsonObject> PendingSceneCandidatePlan;
    FString SessionCandidatePackage;
    FString SessionCandidatePlanId;
    FString SessionCandidatePlanSha;
    FString SessionCandidateStageRequestSha;
    FString SessionCandidateProtectedHash;
};
