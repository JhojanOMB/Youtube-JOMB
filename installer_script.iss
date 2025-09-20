#define MyAppVersion "0.0.0"

[Setup]
AppName=Youtube-JOMB
AppVersion={#MyAppVersion}
AppPublisher=JOMB S.A.S
DefaultDirName={autopf}\Youtube-JOMB
DefaultGroupName=Youtube-JOMB
Compression=lzma
SolidCompression=yes
OutputDir=installer
OutputBaseFilename=Youtube-JOMB_{#MyAppVersion}
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
; Tomamos el exe generado por PyInstaller en dist\youtube.exe
Source: "dist\youtube.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Youtube-JOMB"; Filename: "{app}\youtube.exe"
Name: "{userdesktop}\Youtube-JOMB"; Filename: "{app}\youtube.exe"

[Run]
Filename: "{app}\youtube.exe"; Description: "Abrir Youtube-JOMB"; Flags: nowait postinstall skipifsilent
