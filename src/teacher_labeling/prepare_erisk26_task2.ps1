param(
  [Parameter(Mandatory=$true)]
  [string]$JsonDir,

  [Parameter(Mandatory=$true)]
  [string]$Labels,

  [Parameter(Mandatory=$true)]
  [string]$Output,

  [int]$MaxChars = 12000,

  [switch]$IncludeContextComments,

  [int]$Limit = 0
)

function Add-Fragment($Fragments, [string]$Kind, $Value) {
  if ($null -eq $Value) { return }
  $text = [string]$Value
  $text = $text.Trim()
  if ($text.Length -gt 0) {
    $Fragments.Add("[$Kind] $text") | Out-Null
  }
}

function Add-CommentFragments($Fragments, $Comments, [string]$SubjectId, [bool]$IncludeContextComments) {
  if ($null -eq $Comments) { return }
  foreach ($comment in $Comments) {
    $isTarget = ($comment.target -eq $true) -or ($comment.user_id -eq $SubjectId)
    if ($isTarget -or $IncludeContextComments) {
      $prefix = if ($isTarget) { "target comment" } else { "context comment" }
      Add-Fragment $Fragments $prefix $comment.body
    }
  }
}

function Limit-Text([string]$Text, [int]$MaxChars) {
  if ($MaxChars -le 0 -or $Text.Length -le $MaxChars) {
    return [PSCustomObject]@{ Text = $Text; Truncated = $false }
  }
  $half = [Math]::Floor($MaxChars / 2)
  $head = $Text.Substring(0, $half).TrimEnd()
  $tail = $Text.Substring($Text.Length - $half).TrimStart()
  $marker = "`n`n[... middle omitted for length; beginning and end retained ...]`n`n"
  return [PSCustomObject]@{ Text = $head + $marker + $tail; Truncated = $true }
}

$labelMap = @{}
Get-Content -LiteralPath $Labels | ForEach-Object {
  $parts = $_.Trim() -split '\s+'
  if ($parts.Count -ge 2) {
    $labelMap[$parts[0]] = $parts[1]
  }
}

$files = Get-ChildItem -LiteralPath $JsonDir -Filter *.json -File | Sort-Object Name
if ($Limit -gt 0) {
  $files = $files | Select-Object -First $Limit
}

$rows = New-Object System.Collections.Generic.List[object]
foreach ($file in $files) {
  $subjectId = $file.BaseName
  if (-not $labelMap.ContainsKey($subjectId)) {
    continue
  }
  $data = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
  $fragments = New-Object System.Collections.Generic.List[string]
  foreach ($item in $data) {
    $submission = $item.submission
    if ($null -ne $submission) {
      $isTargetSubmission = ($submission.target -eq $true) -or ($submission.user_id -eq $subjectId)
      if ($isTargetSubmission) {
        Add-Fragment $fragments "submission title" $submission.title
        Add-Fragment $fragments "submission body" $submission.body
      }
      Add-CommentFragments $fragments $submission.comments $subjectId ([bool]$IncludeContextComments)
    }
    Add-CommentFragments $fragments $item.comments $subjectId ([bool]$IncludeContextComments)
  }
  $fullText = ($fragments -join "`n`n")
  if ($fullText.Trim().Length -eq 0) {
    continue
  }
  $limited = Limit-Text $fullText $MaxChars
  $rows.Add([PSCustomObject]@{
    subject_id = $subjectId
    gold_label = $labelMap[$subjectId]
    source = "eRisk26-task2-contextualized-depression"
    text = $limited.Text
    source_file = $file.Name
    writings_included = $fragments.Count
    chars_before_truncation = $fullText.Length
    truncated = $limited.Truncated
  }) | Out-Null
}

$outDir = Split-Path -Parent ([System.IO.Path]::GetFullPath($Output))
if ($outDir) {
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}
$rows | Export-Csv -LiteralPath $Output -NoTypeInformation -Encoding UTF8
Write-Output "wrote=$($rows.Count) output=$Output"
