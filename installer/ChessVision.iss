; Inno Setup script for Chess Vision. Build with installer\build.ps1.
#define AppName "Chess Vision"
#define AppVersion "1.0.0"
#define AppExe "ChessVision.exe"

[Setup]
AppId={{18E3F3FA-22D2-4418-A298-EE9D4D6383AD}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Chess Vision
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Lets the user pick "install for me only" (no admin needed) or "for all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\build\installer
OutputBaseFilename=ChessVision-Setup-{#AppVersion}
SetupIconFile=..\chess_vision.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\build\dist\ChessVision\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Eight Queens"; Filename: "{app}\{#AppExe}"; Parameters: "--queens"
Name: "{group}\Practice board"; Filename: "{app}\{#AppExe}"; Parameters: "--practice"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
