#pragma once

#include "Containers/Ticker.h"
#include "Modules/ModuleManager.h"

class UPCGComponent;

class FArtFlowSceneBridgeModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

private:
    void RegisterMenus();
    void ExportSelectedScene();
    void ReviewLastExport() const;
    bool TickAutomation(float DeltaTime);

    FTSTicker::FDelegateHandle AutomationTickHandle;
    bool bAutomationHandled = false;
    bool bStageGenerationPending = false;
    bool bStageReconciled = false;
    TWeakObjectPtr<UPCGComponent> StagePCGComponent;
    FString StageSourceHash;
    FString StageProtectedHash;
    FString LastExportPath;
};
