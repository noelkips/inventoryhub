param(
    [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Branch = "backup",
    [string]$Remote = "origin"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-BackupLog {
    param([string]$Message)

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $Message"
    Write-Host $line
    Add-Content -Path (Join-Path $RepoPath "backup.log") -Value $line
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $output = & git @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $exitCode.`n$output"
    }

    return [PSCustomObject]@{
        Output = ($output -join "`n").Trim()
        ExitCode = $exitCode
    }
}

if (-not (Test-Path $RepoPath)) {
    throw "Repository path does not exist: $RepoPath"
}

Set-Location $RepoPath

$lockFile = Join-Path $RepoPath ".backup.lock"
if (Test-Path $lockFile) {
    Write-BackupLog "Skipped: another backup process appears to be running."
    exit 0
}

New-Item -ItemType File -Path $lockFile -Force | Out-Null

try {
    $insideRepo = Invoke-Git -Arguments @("rev-parse", "--is-inside-work-tree")
    if ($insideRepo.Output -ne "true") {
        throw "The script must run inside a git working tree."
    }

    $sourceBranch = (Invoke-Git -Arguments @("rev-parse", "--abbrev-ref", "HEAD")).Output

    $fetchResult = Invoke-Git -Arguments @("fetch", $Remote, $Branch) -AllowFailure
    if ($fetchResult.ExitCode -eq 0) {
        Write-BackupLog "Fetched latest '$Branch' from '$Remote'."
    } else {
        Write-BackupLog "Warning: could not fetch '$Branch' from '$Remote'. Continuing with local refs."
    }

    $localBranchExists = (Invoke-Git -Arguments @("show-ref", "--verify", "--quiet", "refs/heads/$Branch") -AllowFailure).ExitCode -eq 0
    $remoteBranchExists = (Invoke-Git -Arguments @("show-ref", "--verify", "--quiet", "refs/remotes/$Remote/$Branch") -AllowFailure).ExitCode -eq 0

    if ($localBranchExists) {
        $baseRef = "refs/heads/$Branch"
    } elseif ($remoteBranchExists) {
        $baseRef = "refs/remotes/$Remote/$Branch"
    } else {
        $baseRef = "HEAD"
    }

    $tempIndex = [System.IO.Path]::GetTempFileName()
    Remove-Item $tempIndex -Force
    New-Item -ItemType File -Path $tempIndex | Out-Null

    $previousIndexFile = $env:GIT_INDEX_FILE
    $env:GIT_INDEX_FILE = $tempIndex

    try {
        Invoke-Git -Arguments @("read-tree", $baseRef) | Out-Null
        Invoke-Git -Arguments @("add", "-A", ".") | Out-Null

        $diffResult = Invoke-Git -Arguments @("diff", "--cached", "--quiet", "--exit-code") -AllowFailure
        if ($diffResult.ExitCode -eq 0) {
            Write-BackupLog "No changes detected. Nothing to back up."
            exit 0
        }
        if ($diffResult.ExitCode -ne 1) {
            throw "Unable to compare staged changes for backup."
        }

        $tree = (Invoke-Git -Arguments @("write-tree")).Output

        if ($localBranchExists) {
            $parentCommit = (Invoke-Git -Arguments @("rev-parse", "refs/heads/$Branch")).Output
        } elseif ($remoteBranchExists) {
            $parentCommit = (Invoke-Git -Arguments @("rev-parse", "refs/remotes/$Remote/$Branch")).Output
        } else {
            $parentCommit = (Invoke-Git -Arguments @("rev-parse", "HEAD")).Output
        }

        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $commitMessage = "Backup snapshot $timestamp from $sourceBranch"
        $commitHash = (
            $commitMessage |
            & git commit-tree $tree -p $parentCommit
        )
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create backup commit."
        }
        $commitHash = ($commitHash -join "`n").Trim()

        Invoke-Git -Arguments @("update-ref", "refs/heads/$Branch", $commitHash) | Out-Null
        Invoke-Git -Arguments @("push", $Remote, "refs/heads/$Branch:refs/heads/$Branch") | Out-Null

        Write-BackupLog "Backup created and pushed to '$Remote/$Branch' at commit $commitHash."
    }
    finally {
        if ($null -ne $previousIndexFile) {
            $env:GIT_INDEX_FILE = $previousIndexFile
        } else {
            Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
        }

        Remove-Item $tempIndex -Force -ErrorAction SilentlyContinue
    }
}
catch {
    Write-BackupLog "Backup failed: $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
}
