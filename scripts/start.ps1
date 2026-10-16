Set-Location (Join-Path $PSScriptRoot '..')
& .\.venv\Scripts\cvti.exe start @args
exit $LASTEXITCODE
