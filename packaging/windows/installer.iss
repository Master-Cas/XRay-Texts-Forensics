#define MyAppName "XRay Texts Forensics"
#define MyAppExeName "XRay-Texts-Forensics.exe"
#define MyAppPublisher "Master-Cas"

#ifndef MyAppVersion
  #define MyAppVersion "0.13.0-alpha"
#endif

#ifndef SourceDir
  #define SourceDir "..\..\dist\XRay-Texts-Forensics"
#endif

#ifndef OutputDir
  #define OutputDir "..\..\dist-installer"
#endif

[Setup]
AppId={{A5E9B1A8-4DD0-4E5A-AB42-7B98C8D7C2A1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\XRay Texts Forensics
DefaultGroupName=XRay Texts Forensics
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=XRay-Texts-Forensics-Windows-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\XRay Texts Forensics"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\XRay Texts Forensics"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch XRay Texts Forensics"; Flags: nowait postinstall skipifsilent
