; Instalador do Painel de Opções (Inno Setup 6). No job Windows, depois dos dois PyInstaller
; (dist\PainelOpcoes e dist\ponte), da raiz do repositório:
;   iscc /DVersao=0.5.0 /DVersaoNome=0.5.0.dev0 /DOrigem=%CD%\dist /DSaida=%CD%\instalador packaging\windows\PainelOpcoes.iss
; Instala por usuário, sem administrador. Os dados (perfis, carteiras, arquivos da B3) ficam em
; %APPDATA%\PainelOpcoes e na pasta de cada perfil: nem atualizar nem desinstalar os apaga.

#ifndef Versao
  #error Passe /DVersao=X.Y.Z (python packaging\windows\versao.py --inno)
#endif
#ifndef VersaoNome
  #define VersaoNome Versao
#endif
#ifndef Origem
  #define Origem "..\..\dist"
#endif
#ifndef Saida
  #define Saida "..\..\instalador"
#endif

[Setup]
; Fixo para sempre: é por ele que a versão nova instala por cima da anterior.
AppId={{B68E5C59-513D-4167-93BB-309549E6ECFC}
AppName=Painel de Opções
AppVersion={#VersaoNome}
VersionInfoVersion={#Versao}
AppPublisher=Hugo Pontello
DefaultDirName={localappdata}\Programs\PainelOpcoes
DisableDirPage=yes
DefaultGroupName=Painel de Opções
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Fecha o app aberto antes de trocar os arquivos.
CloseApplications=yes
OutputDir={#Saida}
OutputBaseFilename=PainelOpcoes-{#VersaoNome}-setup
UninstallDisplayIcon={app}\PainelOpcoes.exe
UninstallDisplayName=Painel de Opções
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; A versão nova troca o programa inteiro: arquivo que saiu dela não fica para trás.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\ponte"

[Files]
Source: "{#Origem}\PainelOpcoes\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Origem}\ponte\*"; DestDir: "{app}\ponte"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Painel de Opções"; Filename: "{app}\PainelOpcoes.exe"
Name: "{autodesktop}\Painel de Opções"; Filename: "{app}\PainelOpcoes.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PainelOpcoes.exe"; Description: "{cm:LaunchProgram,Painel de Opções}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: dirifempty; Name: "{app}"
