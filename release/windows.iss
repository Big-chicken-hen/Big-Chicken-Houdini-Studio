#ifndef Payload
  #error Supply /DPayload with the assembled package directory
#endif
#ifndef BuildId
  #error Supply /DBuildId with the manifest build identifier
#endif
#ifndef Output
  #error Supply /DOutput with the checkout-local output directory
#endif

[Setup]
AppId=BigChickenHoudiniStudio
AppName=Big-Chicken Houdini Studio
AppVersion=0.1.0-rc.1
AppPublisher=Big-chicken-hen
AppPublisherURL=https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio
DefaultDirName={localappdata}\Programs\Big-Chicken Houdini Studio
DefaultGroupName=Big-Chicken Houdini Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.22000
CloseApplications=no
RestartApplications=no
AppMutex=Local\BigChickenStudio.ReleaseInUse
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
OutputDir={#Output}
OutputBaseFilename=Big-Chicken-Studio-{#BuildId}-win-x64
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName=Big-Chicken Houdini Studio
UninstallFilesDir={app}\uninstall
LicenseFile={#Payload}\LICENSE
InfoAfterFile={#Payload}\licenses\THIRD-PARTY-NOTICES.md

[Files]
Source: "{#Payload}\*"; DestDir: "{app}\versions\{#BuildId}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Big-Chicken Houdini Studio"; Filename: "{app}\versions\{#BuildId}\runtime\pythonw.exe"; Parameters: "-I -B ""{app}\versions\{#BuildId}\start_release.pyw"""; WorkingDir: "{app}\versions\{#BuildId}"
Name: "{group}\Uninstall Studio"; Filename: "{uninstallexe}"

; No [UninstallDelete], state/cache scan, process termination, PATH change,
; Houdini configuration edit, credential copy, first-run pip or auto updater.

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if DirExists(ExpandConstant('{app}\versions\{#BuildId}')) then
    Result := 'This exact version already has an installation directory. Open that version, or close Studio sessions and uninstall before repairing it. User state and output are preserved by uninstall.';
end;
