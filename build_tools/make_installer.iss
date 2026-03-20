; GhostScripter-K1-K2 Inno Setup Installer Script
; ==================================================
; Produces a one-click Windows installer (.exe) from the PyInstaller output.
;
; Prerequisites:
;   - Inno Setup 6.x  (https://jrsoftware.org/isinfo.php)
;   - PyInstaller dist folder must exist:  dist\GhostScripter-K1-K2\
;
; Usage:
;   iscc build_tools\make_installer.iss
;   -- or --
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build_tools\make_installer.iss
;
; Output:
;   dist\installer\GhostScripter-K1-K2-v1.0.0-Setup.exe

#define AppName      "GhostScripter-K1-K2"
#define AppVersion   "1.0.0"
#define AppPublisher "GhostScripter Project"
#define AppURL       "https://github.com/YOUR_USERNAME/GhostScripter-K1-K2"
#define AppExeName   "GhostScripter-K1-K2.exe"
#define SourceDir    "..\dist\GhostScripter-K1-K2"
#define IconFile     "..\resources\icons\ghostscripter.ico"
#define LicenseFile  "..\LICENSE"

[Setup]
AppId={{A7B3C9D2-4E1F-4A2B-8C3D-5F6A7B8C9D0E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; The installer output
OutputDir=..\dist\installer
OutputBaseFilename={#AppName}-v{#AppVersion}-Setup
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
; Appearance
WizardStyle=modern
WizardSizePercent=120
SetupIconFile={#IconFile}
; Require Windows 10 or later (64-bit)
MinVersion=10.0.17763
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
; Privileges — install per-user by default (no UAC elevation needed)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog
; Misc
DisableProgramGroupPage=yes
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Installer
VersionInfoTextVersion={#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc_nss"; Description: "Associate .nss files with GhostScripter"; GroupDescription: "File associations"; Flags: unchecked
Name: "fileassoc_dlg"; Description: "Associate .dlg files with GhostScripter"; GroupDescription: "File associations"; Flags: unchecked

[Files]
; Main application folder (everything PyInstaller put in dist\GhostScripter-K1-K2\)
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Top-level docs (also inside bundle, but place copies alongside start menu)
Source: "..\README.md";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\CREDITS.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\resources\icons\ghostscripter.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\resources\icons\ghostscripter.ico"; Tasks: desktopicon

[Registry]
; .nss file association (optional, on task selection)
Root: HKA; Subkey: "Software\Classes\.nss";                         ValueType: string; ValueName: ""; ValueData: "GhostScripterNSS"; Flags: uninsdeletevalue; Tasks: fileassoc_nss
Root: HKA; Subkey: "Software\Classes\GhostScripterNSS";             ValueType: string; ValueName: ""; ValueData: "KotOR NWScript Source"; Flags: uninsdeletekey; Tasks: fileassoc_nss
Root: HKA; Subkey: "Software\Classes\GhostScripterNSS\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: fileassoc_nss
Root: HKA; Subkey: "Software\Classes\GhostScripterNSS\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: fileassoc_nss

; .dlg file association (optional, on task selection)
Root: HKA; Subkey: "Software\Classes\.dlg";                         ValueType: string; ValueName: ""; ValueData: "GhostScripterDLG"; Flags: uninsdeletevalue; Tasks: fileassoc_dlg
Root: HKA; Subkey: "Software\Classes\GhostScripterDLG";             ValueType: string; ValueName: ""; ValueData: "KotOR Dialogue File"; Flags: uninsdeletekey; Tasks: fileassoc_dlg
Root: HKA; Subkey: "Software\Classes\GhostScripterDLG\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: fileassoc_dlg
Root: HKA; Subkey: "Software\Classes\GhostScripterDLG\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: fileassoc_dlg

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\GhostScripter"

[Code]
// Optional: check if GhostRigger is installed and suggest installing it
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
  begin
    WizardForm.WelcomeLabel2.Caption :=
      'This will install GhostScripter-K1-K2 v{#AppVersion} — ' +
      'the all-in-one IDE for modding Knights of the Old Republic 1 & 2 TSL.' + #13#10 + #13#10 +
      'For full 3D model rigging support, also install GhostRigger ' +
      '(the companion tool) from the same GitHub repository.' + #13#10 + #13#10 +
      WizardForm.WelcomeLabel2.Caption;
  end;
end;
