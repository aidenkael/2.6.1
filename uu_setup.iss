; UU护航 Inno Setup 安装脚本
; 生成：UU护航setup.exe

#define MyAppName "UU护航"
#define MyAppVersion "3.0.1"
#define MyAppPublisher "UU护航团队"
#define MyAppURL "https://github.com/UU护航"
#define MyAppExeName "UU护航.exe"
#define MyAppQuickExeName "UU测算.exe"

; 固定 AppId —— 从 3.0.1 开始永久使用，保证升级识别
#define MyAppId "{{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 安装程序图标（黑色 U）
SetupIconFile=src\profit_accounting_26\ui\assets\uu_main_black.ico

; 允许用户选择安装目录
DisableDirPage=no
DefaultDirName={autopf}\{#MyAppName}
AllowNoIcons=yes

; 输出设置
OutputDir=installer_output
OutputBaseFilename=UU护航setup
Compression=lzma2/ultra64
SolidCompression=yes

; 权限
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; UI 风格
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 主程序目录（PyInstaller 输出）
Source: "dist\UU护航\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单 - UU护航（黑色 U）
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\src\profit_accounting_26\ui\assets\uu_main_black.ico"; WorkingDir: "{app}"
; 开始菜单 - UU测算（蓝色 U）
Name: "{group}\{#MyAppQuickExeName}"; Filename: "{app}\{#MyAppQuickExeName}"; IconFilename: "{app}\_internal\src\profit_accounting_26\ui\assets\uu_quick_blue.ico"; WorkingDir: "{app}"
; 开始菜单 - 卸载
Name: "{group}\卸载{#MyAppName}"; Filename: "{uninstallexe}"
; 桌面快捷方式 - UU护航（黑色 U）
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\src\profit_accounting_26\ui\assets\uu_main_black.ico"; WorkingDir: "{app}"; Tasks: desktopicon
; 桌面快捷方式 - UU测算（蓝色 U）
Name: "{autodesktop}\{#MyAppQuickExeName}"; Filename: "{app}\{#MyAppQuickExeName}"; IconFilename: "{app}\_internal\src\profit_accounting_26\ui\assets\uu_quick_blue.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; 安装完成后可选启动主程序
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行{#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 清理安装目录下的所有文件（但不触碰用户数据目录）
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"
Type: files; Name: "{app}\{#MyAppQuickExeName}"
Type: files; Name: "{app}\unins000.exe"
Type: files; Name: "{app}\unins000.dat"
