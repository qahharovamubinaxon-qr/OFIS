; Inno Setup script — builds OFIS_Setup_1.0.0.exe from the PyInstaller output.
; 1) pyinstaller build\ofis.spec --noconfirm      (creates dist\OFIS)
; 2) open this file in Inno Setup 6 (free, jrsoftware.org) and press Compile,
;    or run:  iscc build\installer.iss
; User data is NOT touched by install/uninstall — it lives in %LOCALAPPDATA%\OFIS.

#define AppName "OFIS"
#define AppVersion "1.0.0"
#define AppExe "OFIS.exe"

[Setup]
AppId={{7A3F2C51-OFIS-HRDA-2026-000000000001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=OFIS
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=OFIS_Setup_{#AppVersion}
SetupIconFile=..\resources\icons\ofis.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\OFIS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
