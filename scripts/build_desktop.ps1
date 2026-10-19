$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot 'work\pyinstaller-cache'
$webAssets = (Join-Path $projectRoot 'src/zhishu_inspection/web') + ';zhishu_inspection/web'
$sqlAssets = (Join-Path $projectRoot 'sql') + ';sql'
$buildArgs = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
    '--name', '智数巡检', '--paths', 'src',
    '--distpath', 'work/desktop-dist', '--workpath', 'work/desktop-build',
    '--specpath', 'work',
    '--add-data', $webAssets,
    '--add-data', $sqlAssets,
    '--hidden-import', 'sqlalchemy.dialects.mysql.pymysql',
    '--hidden-import', 'sqlalchemy.dialects.postgresql.psycopg',
    '--hidden-import', 'sqlalchemy.dialects.mssql.pymssql',
    '--hidden-import', 'sqlalchemy.dialects.oracle.oracledb',
    '--collect-all', 'psycopg_binary',
    '--collect-all', 'pymssql',
    '--collect-all', 'oracledb',
    '--hidden-import', 'pymysql', '--hidden-import', 'psycopg',
    '--hidden-import', 'psycopg_binary._psycopg', '--hidden-import', 'psycopg_binary.pq',
    '--hidden-import', 'python_calamine', '--hidden-import', 'olefile',
    '--hidden-import', 'webview.platforms.edgechromium',
    '--hidden-import', 'webview.platforms.winforms',
    '--collect-all', 'webview', '--collect-all', 'pythonnet', '--collect-all', 'clr_loader',
    'scripts/desktop_entry.py'
)
& $python @buildArgs
if ($LASTEXITCODE -ne 0) { throw '桌面程序打包失败' }
