param(
  [Parameter(Mandatory=$true)]
  [string]$InputMarkdown,

  [Parameter(Mandatory=$true)]
  [string]$OutputDocx
)

Add-Type -AssemblyName System.IO.Compression

function Escape-XmlText([string]$Text) {
  if ($null -eq $Text) { return "" }
  return [System.Security.SecurityElement]::Escape($Text)
}

function Add-ZipEntryText($Zip, [string]$Name, [string]$Text) {
  $entry = $Zip.CreateEntry($Name)
  $stream = $entry.Open()
  try {
    $writer = New-Object System.IO.StreamWriter($stream, [System.Text.Encoding]::UTF8)
    try { $writer.Write($Text) } finally { $writer.Dispose() }
  } finally { $stream.Dispose() }
}

function Add-ZipEntryFile($Zip, [string]$Name, [string]$Path) {
  $entry = $Zip.CreateEntry($Name)
  $stream = $entry.Open()
  try {
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $stream.Write($bytes, 0, $bytes.Length)
  } finally { $stream.Dispose() }
}

function New-Paragraph([string]$Text, [string]$Style = "Normal") {
  $escaped = Escape-XmlText $Text
  $styleXml = ""
  if ($Style -and $Style -ne "Normal") {
    $styleXml = "<w:pPr><w:pStyle w:val=`"$Style`"/></w:pPr>"
  }
  return "<w:p>$styleXml<w:r><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>"
}

function New-CodeParagraph([string]$Text) {
  $escaped = Escape-XmlText $Text
  return "<w:p><w:pPr><w:pStyle w:val=`"Code`"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii=`"Consolas`" w:hAnsi=`"Consolas`"/></w:rPr><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>"
}

function New-ImageParagraph([string]$RelId, [string]$Alt, [int]$ImageId) {
  $safeAlt = Escape-XmlText $Alt
  $cx = 6600000
  $cy = 2750000
  return @"
<w:p>
  <w:pPr><w:jc w:val="center"/></w:pPr>
  <w:r>
    <w:drawing>
      <wp:inline distT="0" distB="0" distL="0" distR="0">
        <wp:extent cx="$cx" cy="$cy"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:docPr id="$ImageId" name="$safeAlt" descr="$safeAlt"/>
        <wp:cNvGraphicFramePr>
          <a:graphicFrameLocks noChangeAspect="1"/>
        </wp:cNvGraphicFramePr>
        <a:graphic>
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:pic>
              <pic:nvPicPr>
                <pic:cNvPr id="$ImageId" name="$safeAlt"/>
                <pic:cNvPicPr/>
              </pic:nvPicPr>
              <pic:blipFill>
                <a:blip r:embed="$RelId"/>
                <a:stretch><a:fillRect/></a:stretch>
              </pic:blipFill>
              <pic:spPr>
                <a:xfrm>
                  <a:off x="0" y="0"/>
                  <a:ext cx="$cx" cy="$cy"/>
                </a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
              </pic:spPr>
            </pic:pic>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing>
  </w:r>
</w:p>
"@
}

function Convert-MarkdownInline([string]$Text) {
  $t = $Text
  $t = $t -replace '^\s*[-*]\s+', '- '
  $t = $t -replace '^\s*\d+\.\s+', ''
  $t = $t -replace '\*\*([^*]+)\*\*', '$1'
  $t = $t -replace '`([^`]+)`', '$1'
  $t = $t -replace '\[([^\]]+)\]\([^)]+\)', '$1'
  return $t
}

$resolvedMd = Resolve-Path -LiteralPath $InputMarkdown
$mdDir = Split-Path -Parent $resolvedMd.Path
$markdown = Get-Content -LiteralPath $resolvedMd.Path -Raw -Encoding UTF8
$lines = $markdown -split "`r?`n"
$title = [System.IO.Path]::GetFileNameWithoutExtension($resolvedMd.Path)

$paras = New-Object System.Collections.Generic.List[string]
$images = New-Object System.Collections.Generic.List[object]
$relationships = New-Object System.Collections.Generic.List[string]
$paras.Add((New-Paragraph $title "Title"))
$inCode = $false
$imageIndex = 1

foreach ($raw in $lines) {
  $line = $raw.TrimEnd()
  if ($line -match '^```') {
    if (-not $inCode) {
      $inCode = $true
      $lang = ($line -replace '^```', '').Trim()
      if ($lang) { $paras.Add((New-CodeParagraph "[$lang]")) }
    } else {
      $inCode = $false
    }
    continue
  }

  if ($inCode) {
    $paras.Add((New-CodeParagraph $line))
    continue
  }

  if ($line -match '^!\[([^\]]*)\]\(([^)]+)\)') {
    $alt = $Matches[1]
    $imgPath = $Matches[2]
    $fullImgPath = [System.IO.Path]::GetFullPath((Join-Path $mdDir $imgPath))
    if (Test-Path -LiteralPath $fullImgPath) {
      $relId = "rIdImage$imageIndex"
      $mediaName = "word/media/image$imageIndex.svg"
      $images.Add([PSCustomObject]@{ MediaName = $mediaName; Path = $fullImgPath })
      $relationships.Add("<Relationship Id=`"$relId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image`" Target=`"media/image$imageIndex.svg`"/>")
      $paras.Add((New-ImageParagraph $relId $alt $imageIndex))
      $paras.Add((New-Paragraph ("Figure: " + $alt) "Caption"))
      $imageIndex += 1
    } else {
      $paras.Add((New-Paragraph ("[Missing figure: " + $imgPath + "]") "Caption"))
    }
    continue
  }

  if ($line.Trim().Length -eq 0) {
    $paras.Add("<w:p/>")
  } elseif ($line -match '^#\s+(.+)$') {
    $paras.Add((New-Paragraph (Convert-MarkdownInline $Matches[1]) "Heading1"))
  } elseif ($line -match '^##\s+(.+)$') {
    $paras.Add((New-Paragraph (Convert-MarkdownInline $Matches[1]) "Heading2"))
  } elseif ($line -match '^###\s+(.+)$') {
    $paras.Add((New-Paragraph (Convert-MarkdownInline $Matches[1]) "Heading3"))
  } elseif ($line -match '^\s*[-*]\s+(.+)$') {
    $paras.Add((New-Paragraph (Convert-MarkdownInline $line) "ListItem"))
  } elseif ($line -match '^\|') {
    $paras.Add((New-CodeParagraph $line))
  } else {
    $paras.Add((New-Paragraph (Convert-MarkdownInline $line) "Normal"))
  }
}

$body = $paras -join ""
$relXml = $relationships -join "`n  "

$contentTypes = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="svg" ContentType="image/svg+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
'@

$rels = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
'@

$docRels = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  $relXml
</Relationships>
"@

$styles = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="120"/></w:pPr><w:rPr><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:after="300"/></w:pPr><w:rPr><w:b/><w:color w:val="0F172A"/><w:sz w:val="42"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="300" w:after="140"/><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="3" w:color="CBD5E1"/></w:pBdr></w:pPr><w:rPr><w:b/><w:color w:val="0F172A"/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="230" w:after="100"/></w:pPr><w:rPr><w:b/><w:color w:val="1E3A8A"/><w:sz w:val="27"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="170" w:after="80"/></w:pPr><w:rPr><w:b/><w:color w:val="334155"/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListItem"><w:name w:val="List Item"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360" w:hanging="180"/><w:spacing w:after="80"/></w:pPr><w:rPr><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:after="220"/></w:pPr><w:rPr><w:i/><w:color w:val="475569"/><w:sz w:val="18"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="60" w:after="80"/><w:ind w:left="180"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:color w:val="1F2937"/><w:sz w:val="18"/></w:rPr></w:style>
</w:styles>
'@

$document = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    $body
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1008" w:right="720" w:bottom="1008" w:left="720" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"@

$outDir = Split-Path -Parent ([System.IO.Path]::GetFullPath($OutputDocx))
if ($outDir) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
if (Test-Path -LiteralPath $OutputDocx) { Remove-Item -LiteralPath $OutputDocx -Force }

$fs = [System.IO.File]::Open($OutputDocx, [System.IO.FileMode]::CreateNew)
try {
  $zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create, $false)
  try {
    Add-ZipEntryText $zip "[Content_Types].xml" $contentTypes
    Add-ZipEntryText $zip "_rels/.rels" $rels
    Add-ZipEntryText $zip "word/_rels/document.xml.rels" $docRels
    Add-ZipEntryText $zip "word/document.xml" $document
    Add-ZipEntryText $zip "word/styles.xml" $styles
    foreach ($img in $images) {
      Add-ZipEntryFile $zip $img.MediaName $img.Path
    }
  } finally { $zip.Dispose() }
} finally { $fs.Dispose() }

Write-Output $OutputDocx
