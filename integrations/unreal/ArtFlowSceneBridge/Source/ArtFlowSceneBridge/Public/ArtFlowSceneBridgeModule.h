#pragma once

#include "Containers/Ticker.h"
#include "Modules/ModuleManager.h"

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
    FString LastExportPath;
};
