; Fish Counter Review Installer (Inno Setup)

[Setup]
AppName=Fish Counter Review
AppVersion=1.0.0
DefaultDirName={userpf}\FishCounterReview
DefaultGroupName=Fish Counter Review
DisableDirPage=no
DisableProgramGroupPage=yes
OutputBaseFilename=FishCounterReviewSetup
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\dist\FishCounterReview\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{commondesktop}\Fish Counter Review"; Filename: "{app}\FishCounterReview.exe"
Name: "{group}\Fish Counter Review"; Filename: "{app}\FishCounterReview.exe"

[Run]
Filename: "{app}\FishCounterReview.exe"; Description: "Launch Fish Counter Review"; Flags: nowait postinstall skipifsilent
