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
; Relativo à pasta deste .iss.
SetupIconFile=..\icone\painel-opcoes.ico

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
; Atualização automática (silenciosa): o app que baixou este instalador pede a reabertura com
; /RELANCAR=1; o parâmetro avisa o app novo de que ele acabou de ser atualizado.
Filename: "{app}\PainelOpcoes.exe"; Parameters: "--depois-de-atualizar"; Flags: nowait; Check: Relancar
Filename: "{app}\PainelOpcoes.exe"; Description: "{cm:LaunchProgram,Painel de Opções}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Code]
const
  SYNCHRONIZE = $00100000;

function OpenProcess(dwDesiredAccess: Cardinal; bInheritHandle: Cardinal; dwProcessId: Cardinal): Cardinal;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(hHandle: Cardinal; dwMilliseconds: Cardinal): Cardinal;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(hObject: Cardinal): Cardinal;
  external 'CloseHandle@kernel32.dll stdcall';

{ Só a atualização silenciosa pede a reabertura; quem instala pelo assistente usa a caixa de
  "Executar o Painel de Opções" da última página. }
function Relancar: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELANCAR|0}') = '1');
end;

{ O app que se atualiza abre este instalador com /ESPERAR=<pid> e sai logo depois. Esperar o
  processo terminar (até 60 s) evita copiar por cima de arquivos ainda em uso. Se o processo já
  saiu (OpenProcess devolve 0), não há o que esperar. }
function InitializeSetup: Boolean;
var
  Pid, Processo: Cardinal;
begin
  Pid := StrToIntDef(ExpandConstant('{param:ESPERAR|0}'), 0);
  if Pid <> 0 then
  begin
    Processo := OpenProcess(SYNCHRONIZE, 0, Pid);
    if Processo <> 0 then
    begin
      WaitForSingleObject(Processo, 60000);
      CloseHandle(Processo);
    end;
  end;
  Result := True;
end;
