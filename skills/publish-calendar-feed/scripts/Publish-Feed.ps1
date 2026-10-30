[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$PublishRepo,
    [string]$Python = "python",
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*\.ics$')][string]$FeedName = "study-plan.ics",
    [switch]$Publish
)

$ErrorActionPreference = "Stop"
$Repository = (Resolve-Path -LiteralPath $PublishRepo).Path
$Source = (Resolve-Path -LiteralPath $InputPath).Path
$Generator = Join-Path $PSScriptRoot "build_feed.py"
$Destination = Join-Path $Repository $FeedName
$LockPath = Join-Path $Repository ".git/calendar-feed-publish.lock"
$Lock = $null

function Invoke-GitChecked {
    param([string[]]$GitArguments)
    # Windows PowerShell treats native stderr progress as ErrorRecords.
    $SavedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $Result = & git -C $Repository @GitArguments 2>&1
        $Code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $SavedPreference
    }
    if ($Code -ne 0) { throw "Git failed ($Code): $($Result -join [Environment]::NewLine)" }
    $Result | ForEach-Object { "$_" }
}

try {
    $TopLevel = Invoke-GitChecked @("rev-parse", "--show-toplevel")
    if ([IO.Path]::GetFullPath($TopLevel) -ne [IO.Path]::GetFullPath($Repository)) {
        throw "PublishRepo must be the repository root."
    }
    # Use the real git directory so linked worktrees are supported too.
    $GitDirectory = Invoke-GitChecked @("rev-parse", "--absolute-git-dir")
    $LockPath = Join-Path $GitDirectory "calendar-feed-publish.lock"
    $Lock = [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)

    if ($Publish) {
        $null = Invoke-GitChecked @("symbolic-ref", "--quiet", "--short", "HEAD")
        $null = Invoke-GitChecked @("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        $Dirty = Invoke-GitChecked @("status", "--porcelain", "--untracked-files=all")
        if ($Dirty) { throw "Publish checkout has existing changes. Review them before publishing." }
        $TextAttribute = Invoke-GitChecked @("check-attr", "text", "--", $FeedName)
        if ($TextAttribute -match ': (set|auto)$') {
            throw "The repository normalizes ICS line endings. Set '*.ics -text' in .gitattributes first."
        }
        $AheadFiles = Invoke-GitChecked @("log", "--format=", "--name-only", "@{upstream}..HEAD")
        $ForeignFiles = @($AheadFiles | Where-Object { $_.Trim() -and $_.Trim() -ne $FeedName })
        if ($ForeignFiles.Count -gt 0) {
            throw "Unpushed commits include unrelated files. Review them before publishing."
        }
    }

    & $Python $Generator --input $Source --output $Destination
    if ($LASTEXITCODE -ne 0) { throw "Feed generation failed; publication stopped." }
    if (-not $Publish) {
        Write-Host "Generated locally. Use -Publish only when publication is authorized."
        return
    }

    # An inherited core.autocrlf=true would otherwise publish LF instead of ICS CRLF.
    $null = Invoke-GitChecked @("-c", "core.autocrlf=false", "add", "--", $FeedName)
    $AllStaged = Invoke-GitChecked @("diff", "--cached", "--name-only")
    if (@($AllStaged | Where-Object { $_ -ne $FeedName }).Count -gt 0) {
        throw "Other files became staged during publication; stopped before commit."
    }
    $Staged = Invoke-GitChecked @("diff", "--cached", "--name-only", "--", $FeedName)
    if ($Staged) {
        # Commit the verified index; a path argument would re-stage with global conversion rules.
        Invoke-GitChecked @("commit", "-m", "Update calendar feed") | Write-Host
    } else {
        Write-Host "No feed changes to commit."
    }
    # Also retries a previous committed feed update whose push failed.
    Invoke-GitChecked @("push") | Write-Host
    Write-Host "Git push finished. Verify the Pages URL separately; device delivery is unverified."
} finally {
    if ($null -ne $Lock) { $Lock.Dispose() }
    # Keep the empty lock file: deleting it could race with the next process.
}
