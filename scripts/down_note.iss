; 低落日记 安装包脚本（Inno Setup 6.5+）
; 编译：ISCC.exe scripts/down_note.iss（build.py 在找到 ISCC 时自动调用）
; 产物：dist/down_note-v0.1.0-setup.exe
; 用户数据（%APPDATA%\down_note）不属于 {app}，卸载/重装都不会动到日记。

#define MyAppName "低落日记"
#define MyAppVersion "0.1.0"
#define MyAppExe "down_note.exe"

[Setup]
AppId={{A3C8E1F4-5B27-4D69-8A0C-91D2E7F45B38}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={userpf}\DownNote
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=down_note-v0.1.0-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExe}
ShowLanguageDialog=auto
CloseApplications=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; PyInstaller onedir 产物（build.py 先生成），整目录进 {app}
Source: "..\dist\down_note\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
