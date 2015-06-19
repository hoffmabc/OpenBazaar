
$validArgs = @('clean', 'exe')

$local = Get-Location;
$bin = Join-Path $local "bin"

if(($args.Count -ge 1) -and (!$validArgs.contains($args[0])))
{
    echo 'Valid usage:'
    echo 'configure.ps1 [clean|exe]'
    return
}

$pythonDir = "$bin\python27"
$gnupgDir = "$bin\GnuPG"
$openSSLDir = "$bin\OpenSSL"
$packagesDir = "$pythonDir\Lib\site-packages"
$python = "$pythonDir\python.exe"
$pip = "$pythonDir\Scripts\pip.exe"
$gpg = "$gnupgDir\pub\gpg.exe"
$libeay = "$openSSLDir\bin\libeay32.dll"
$miniupnpc = "$packagesDir\miniupnpc.pyd"

$pythonUrl = "https://www.python.org/ftp/python/2.7.9/python-2.7.9.msi"
$gpgUrl = "http://files.gpg4win.org/gpg4win-light-2.2.4.exe"
$opensslUrl = "https://slproweb.com/download/Win32OpenSSL-1_0_2c.exe" #yes this is the official openssl for windows
$getpipUrl = "https://bootstrap.pypa.io/get-pip.py"
$setupsDir =  "$bin\setups"
$pythonSetup = "$setupsDir\python-2.7.9.msi"
$gpgSetup = "$setupsDir\gpg4win-light-2.2.4.exe"
$openSSLSetup = "$setupsDir\Win32OpenSSL-1_0_2a.exe"
$getPip = "$setupsDir\get-pip.py"

$gpg4win_config = @"
[gpg4win]
    ; Installer settings.  Do not define or leave empty for defaults.
    inst_gnupg2 = false
    inst_gpgol = false
    inst_gpgex = false
    inst_gpa = false
    inst_winpt = false
    inst_gpgee = false
    inst_claws_mail = false
    inst_novice_manual_en = false
    inst_novice_manual_de = false
    inst_advanced_manual_de = false

    ; Where to install short-cuts.
    inst_start_menu = false
    inst_desktop = false
    inst_quick_launch_bar = false
"@

Function CheckCompiler
{
    if((Test-Path Env:\VS90COMNTOOLS) -eq 0)
    {
        echo ''
        echo 'ERROR: Could not detect Visual Studio 2008.'
        echo 'You should download and install VS2008 before proceeding to compile the depedencies yourself'
        echo 'Visual Studio 2008 Express edition is available here: go.microsoft.com/?linkid=7729279'
        echo ''
        Exit
    }
}

Function DownloadFile ($message, $file, $url)
{
    if((Test-Path $file) -eq 0)
    {
        echo $message
        Invoke-WebRequest $url -OutFile $file
    }
}

Function Configure
{
   if((Test-Path $setupsDir) -eq 0)
    {
        New-Item -ItemType directory -Path $setupsDir
    }

    if((Test-Path $pythonDir) -eq 0)
    {
        DownloadFile "Downloading python installer..." $pythonSetup $pythonUrl
        echo "Installing Python 2.7"
        Start-Process msiexec.exe -Wait "/qn /a $pythonSetup  TARGETDIR=$pythonDir"
    }

    if((Test-Path $gpg) -eq 0)
    {
        DownloadFile "Downloading pgp4win installer..." $gpgSetup $gpgUrl
        echo "Installing gpg4win 2.2.4"
        $gpg4win_config | Out-File "$setupsDir\gpgInstall.ini"
        Start-Process $gpgSetup -Wait "/S /C=$configFile /D=$gnupgDir"
    }

    if((Test-Path $openSSLDir) -eq 0)
    {
        DownloadFile "Downloading OpenSSL installer..." $openSSLSetup $opensslUrl
        echo "Installing OpenSSL"
        Start-Process $openSSLSetup -Wait "/silent /verysilent /sp- /suppressmsgboxes /DIR=$openSSLDir"
    }

    if((Test-Path $pip) -eq 0)
    {
        DownloadFile "Downloading get-pip.py..." $getPip $getpipUrl
        Start-Process $python -Wait -NoNewWindow $getPip
    }

    Start-Process $pip -Wait  -NoNewWindow "install http://sourceforge.net/projects/py2exe/files/latest/download?source=files"
    Start-Process $pip -Wait  -NoNewWindow "install py2exe2msi"
    Start-Process $pip -Wait  -NoNewWindow "install https://github.com/yagoulas/miniupnp/zipball/msvc_miniupnpc"
    Start-Process $pip -Wait  -NoNewWindow "install -r requirements.txt"
}

Function Clean
{
    if((Test-Path $bin) -ne 0)
    {
        echo "Deleting $bin folder"
        if((Test-Path $pythonDir) -ne 0)
        {
            Remove-Item $pythonDir -Recurse
        }
        if((Test-Path $openSSLDir) -ne 0)
        {
            Remove-Item $openSSLDir -Recurse
        }
        if((Test-Path $gpg) -ne 0)
        {
            Start-Process "$gnupgDir\gpg4win-uninstall.exe" -Wait " /S"
        }
        if((Test-Path ".\installers\windows\build") -ne 0)
        {
            Remove-Item ".\installers\windows\build" -Recurse
        }
        if((Test-Path ".\installers\windows\dist") -ne 0)
        {
            Remove-Item ".\installers\windows\dist"  -Recurse
        }
    }
}

$pycountryUrl = "https://pypi.python.org/packages/source/p/pycountry/pycountry-1.8.zip"
$pycountryZip = "$setupsDir\pycountry-1.8.zip"
$pyCountry = "$setupsDir\pycountry-1.8"
$pycountryEgg = "pycountry-1.8-py2.7.egg"

Function MakeExe
{
    if((Test-Path $packagesDir\zope\__init__.py) -eq 0)
    {
        New-Item $packagesDir\zope\__init__.py -type file
    }

    if((Test-Path ".\$pycountryEgg") -eq 0)
    {
        DownloadFile "Downloading pycountry-1.8.zip..." $pycountryZip $pycountryUrl
        [Reflection.Assembly]::LoadWithPartialName( "System.IO.Compression.FileSystem" )
        [System.IO.Compression.ZipFile]::ExtractToDirectory($pycountryZip, $setupsDir)
        cd $pyCountry
        Start-Process $python -Wait -NoNewWindow "setup.py bdist_egg"
        cd $local
        Copy-Item "$pyCountry\dist\$pycountryEgg" $local
    }

    cd ".\installers\windows\"
    Start-Process $python -Wait -NoNewWindow "setup.py py2exe"
    cd ..
    cd ..
}

if($args -eq 'clean')
{
    Clean
}
elseif($args.Count -eq 0)
{
    Configure
}
elseif ($args -eq 'exe')
{
    MakeExe
}
