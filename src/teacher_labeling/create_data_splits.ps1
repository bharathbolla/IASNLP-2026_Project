param(
  [Parameter(Mandatory=$true)]
  [string]$InputPath,

  [Parameter(Mandatory=$true)]
  [string]$OutputDir,

  [string]$IdColumn = "User",
  [string]$GroupColumn = "User",
  [string]$LabelColumn = "Label",
  [string]$SplitColumn = "split",
  [double]$TrainRatio = 0.70,
  [double]$DevRatio = 0.15,
  [int]$Seed = 42
)

function Get-StableRandomValue([string]$Value, [int]$Seed) {
  $bytes = [System.Text.Encoding]::UTF8.GetBytes("$Seed::$Value")
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $hash = $sha.ComputeHash($bytes)
    return [BitConverter]::ToUInt32($hash, 0)
  } finally {
    $sha.Dispose()
  }
}

function Add-SplitProperty($Row, [string]$SplitColumn, [string]$Split) {
  $copy = [ordered]@{}
  foreach ($prop in $Row.PSObject.Properties) {
    $copy[$prop.Name] = $prop.Value
  }
  $copy[$SplitColumn] = $Split
  return [PSCustomObject]$copy
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$rows = Import-Csv -LiteralPath $InputPath
if (-not $rows -or $rows.Count -eq 0) {
  throw "No rows found in $InputPath"
}

$groups = $rows | Group-Object { if ($_.($GroupColumn)) { $_.($GroupColumn) } elseif ($_.($IdColumn)) { $_.($IdColumn) } else { [guid]::NewGuid().ToString() } }
$labelBuckets = @{}
foreach ($group in $groups) {
  $labels = $group.Group | ForEach-Object { $_.($LabelColumn) }
  $majorityLabel = ($labels | Group-Object | Sort-Object Count -Descending | Select-Object -First 1).Name
  if (-not $labelBuckets.ContainsKey($majorityLabel)) {
    $labelBuckets[$majorityLabel] = New-Object System.Collections.Generic.List[object]
  }
  $labelBuckets[$majorityLabel].Add($group)
}

$splitForGroup = @{}
foreach ($label in $labelBuckets.Keys) {
  $bucket = $labelBuckets[$label] | Sort-Object { Get-StableRandomValue $_.Name $Seed }
  $n = $bucket.Count
  $trainN = [Math]::Round($n * $TrainRatio)
  $devN = [Math]::Round($n * $DevRatio)
  if (($trainN + $devN) -gt $n) {
    $devN = [Math]::Max(0, $n - $trainN)
  }
  for ($i = 0; $i -lt $n; $i++) {
    $split = if ($i -lt $trainN) { "train" } elseif ($i -lt ($trainN + $devN)) { "dev" } else { "test" }
    $splitForGroup[$bucket[$i].Name] = $split
  }
}

$splitRows = @{
  train = New-Object System.Collections.Generic.List[object]
  dev = New-Object System.Collections.Generic.List[object]
  test = New-Object System.Collections.Generic.List[object]
}

foreach ($group in $groups) {
  $split = $splitForGroup[$group.Name]
  foreach ($row in $group.Group) {
    $splitRows[$split].Add((Add-SplitProperty $row $SplitColumn $split))
  }
}

$allRows = New-Object System.Collections.Generic.List[object]
foreach ($split in @("train", "dev", "test")) {
  $path = Join-Path $OutputDir "$split.csv"
  $splitRows[$split] | Export-Csv -LiteralPath $path -NoTypeInformation -Encoding UTF8
  foreach ($row in $splitRows[$split]) {
    $allRows.Add($row)
  }
}

$allPath = Join-Path $OutputDir "all_with_splits.csv"
$allRows | Export-Csv -LiteralPath $allPath -NoTypeInformation -Encoding UTF8

$manifest = [ordered]@{
  input = $InputPath
  seed = $Seed
  train_ratio = $TrainRatio
  dev_ratio = $DevRatio
  test_ratio = [Math]::Round(1.0 - $TrainRatio - $DevRatio, 6)
  group_column = $GroupColumn
  label_column = $LabelColumn
  counts = [ordered]@{
    train = $splitRows.train.Count
    dev = $splitRows.dev.Count
    test = $splitRows.test.Count
  }
  label_counts = [ordered]@{}
  note = "The test split is a locked evaluation candidate. For gold results, manually review/relabel it with the project rubric and evidence spans before use."
}

foreach ($split in @("train", "dev", "test")) {
  $counts = [ordered]@{}
  foreach ($g in ($splitRows[$split] | Group-Object $LabelColumn | Sort-Object Name)) {
    $counts[$g.Name] = $g.Count
  }
  $manifest.label_counts[$split] = $counts
}

$manifestPath = Join-Path $OutputDir "split_manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
$manifest | ConvertTo-Json -Depth 8
