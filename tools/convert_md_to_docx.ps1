param(
  [Parameter(Mandatory=$true)]
  [string[]]$InputPaths,

  [Parameter(Mandatory=$true)]
  [string]$OutputDir
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
    try {
      $writer.Write($Text)
    } finally {
      $writer.Dispose()
    }
  } finally {
    $stream.Dispose()
  }
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

function Convert-MarkdownInline([string]$Text) {
  $t = $Text
  $t = $t -replace '^\s*[-*]\s+', '- '
  $t = $t -replace '^\s*\d+\.\s+', ''
  $t = $t -replace '\*\*([^*]+)\*\*', '$1'
  $t = $t -replace '`([^`]+)`', '$1'
  $t = $t -replace '\[([^\]]+)\]\([^)]+\)', '$1'
  return $t
}

function Convert-MarkdownToBodyXml([string]$Markdown, [string]$Title) {
  $lines = $Markdown -split "`r?`n"
  $paras = New-Object System.Collections.Generic.List[string]
  $paras.Add((New-Paragraph $Title "Title"))
  $inCode = $false
  $codeLang = ""

  foreach ($raw in $lines) {
    $line = $raw.TrimEnd()
    if ($line -match '^```') {
      if (-not $inCode) {
        $inCode = $true
        $codeLang = ($line -replace '^```', '').Trim()
        if ($codeLang) { $paras.Add((New-CodeParagraph "[$codeLang]")) }
      } else {
        $inCode = $false
        $codeLang = ""
      }
      continue
    }

    if ($inCode) {
      $paras.Add((New-CodeParagraph $line))
      continue
    }

    if ($line.Trim().Length -eq 0) {
      $paras.Add("<w:p/>")
      continue
    }

    if ($line -match '^#\s+(.+)$') {
      $paras.Add((New-Paragraph (Convert-MarkdownInline $Matches[1]) "Heading1"))
    } elseif ($line -match '^##\s+(.+)$') {
      $paras.Add((New-Paragraph (Convert-MarkdownInline $Matches[1]) "Heading2"))
    } elseif ($line -match '^###\s+(.+)$') {
      $paras.Add((New-Paragraph (Convert-MarkdownInline $Matches[1]) "Heading3"))
    } elseif ($line -match '^####\s+(.+)$') {
      $paras.Add((New-Paragraph (Convert-MarkdownInline $Matches[1]) "Heading4"))
    } elseif ($line -match '^\|') {
      $paras.Add((New-CodeParagraph $line))
    } else {
      $paras.Add((New-Paragraph (Convert-MarkdownInline $line) "Normal"))
    }
  }

  return ($paras -join "")
}

function New-DocxFromMarkdown([string]$InputPath, [string]$OutputPath) {
  $resolved = Resolve-Path -LiteralPath $InputPath
  $markdown = Get-Content -LiteralPath $resolved -Raw -Encoding UTF8
  $title = [System.IO.Path]::GetFileNameWithoutExtension($resolved.Path)
  $body = Convert-MarkdownToBodyXml $markdown $title

  $contentTypes = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
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

  $docRels = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
'@

  $styles = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="40" w:after="40"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="18"/></w:rPr></w:style>
</w:styles>
'@

  $document = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    $body
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1008" w:right="1008" w:bottom="1008" w:left="1008" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"@

  if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
  }
  $fs = [System.IO.File]::Open($OutputPath, [System.IO.FileMode]::CreateNew)
  try {
    $zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create, $false)
    try {
      Add-ZipEntryText $zip "[Content_Types].xml" $contentTypes
      Add-ZipEntryText $zip "_rels/.rels" $rels
      Add-ZipEntryText $zip "word/_rels/document.xml.rels" $docRels
      Add-ZipEntryText $zip "word/document.xml" $document
      Add-ZipEntryText $zip "word/styles.xml" $styles
    } finally {
      $zip.Dispose()
    }
  } finally {
    $fs.Dispose()
  }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

foreach ($inputPath in $InputPaths) {
  $resolved = Resolve-Path -LiteralPath $inputPath
  $base = [System.IO.Path]::GetFileNameWithoutExtension($resolved.Path)
  $output = Join-Path $OutputDir ($base + ".docx")
  New-DocxFromMarkdown $resolved.Path $output
  Write-Output $output
}

