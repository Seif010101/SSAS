; Inno Setup script: builds SSAS-Studio-Setup-<version>.exe from dist\SSAS Studio
#ifndef AppVersion
  #define AppVersion "0.1.2"
#endif

[Setup]
AppId={{6B1E2C4A-9F5B-4C3E-9D1A-55A5C0D2F7E1}
AppName=SSAS Studio
AppVersion={#AppVersion}
AppPublisher=SSAS
DefaultDirName={autopf}\SSAS Studio
DefaultGroupName=SSAS Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=SSAS-Studio-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\SSAS Studio.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\SSAS Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SSAS Studio"; Filename: "{app}\SSAS Studio.exe"
Name: "{group}\Uninstall SSAS Studio"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SSAS Studio"; Filename: "{app}\SSAS Studio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SSAS Studio.exe"; Description: "Start SSAS Studio"; Flags: nowait postinstall skipifsilent
