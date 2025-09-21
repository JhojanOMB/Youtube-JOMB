; installer_script.iss
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#ifndef MyAppVerName
  #define MyAppVerName MyAppVersion
#endif

[Setup]
; AppName y versión (aseguro AppVersion y AppVerName ambos presentes)
AppName=Youtube-JOMB
AppVersion={#MyAppVersion}
AppVerName={#MyAppVerName}
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
; Copia el ejecutable compilado
Source: "dist\Youtube-JOMB.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Youtube JOMB"; Filename: "{app}\Youtube-JOMB.exe"
Name: "{desktop}\Youtube JOMB"; Filename: "{app}\Youtube-JOMB.exe"

[Run]
Filename: "{app}\Youtube-JOMB.exe"; Description: "Abrir Youtube-JOMB"; Flags: nowait postinstall skipifsilent
