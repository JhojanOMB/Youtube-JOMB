#ifndef MyAppVersion
#define MyAppVersion "0.0.0"
#endif

[Setup]
AppName=YouTube Downloader - JOMB
AppVersion={#MyAppVersion}
AppPublisher=JOMB S.A.S
DefaultDirName={autopf}\YouTube Downloader
DefaultGroupName=YouTube Downloader
Compression=lzma
SolidCompression=yes
OutputDir=installer
OutputBaseFilename=YouTubeDownloaderSetup_{#MyAppVersion}
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
; Busca youtube.exe en la raíz del repo (generado por pyinstaller --distpath .)
Source: "youtube.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\YouTube Downloader"; Filename: "{app}\youtube.exe"
Name: "{userdesktop}\YouTube Downloader"; Filename: "{app}\youtube.exe"

[Run]
Filename: "{app}\youtube.exe"; Description: "Abrir YouTube Downloader"; Flags: nowait postinstall skipifsilent
