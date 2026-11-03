param([string]$Book, [string]$OutJson)
# Выгружает из книги Excel листы заявок («Заявка», «Водитель МГ») в JSON: текст, жирность, объединение, формула.
# Плюс «отпечаток» всех листов (значения + формулы), чтобы проверить, что ТН не изменились.
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
try {
  $wb = $xl.Workbooks.Open($Book, 0, $true)
  $res = [ordered]@{ sheets = [ordered]@{}; fingerprint = [ordered]@{} }
  foreach ($ws in $wb.Worksheets) {
    $ur = $ws.UsedRange
    $vals = $ur.Value2; $forms = $ur.Formula
    $sb = New-Object System.Text.StringBuilder
    $nf = 0
    for ($r = 1; $r -le $ur.Rows.Count; $r++) { for ($c = 1; $c -le $ur.Columns.Count; $c++) {
      $f = "$($forms[$r,$c])"; if ($f.StartsWith("=")) { $nf++ }
      [void]$sb.Append("$($vals[$r,$c])|$f;") } }
    $md5 = [BitConverter]::ToString([Security.Cryptography.MD5]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($sb.ToString())))
    $res.fingerprint[$ws.Name] = [ordered]@{ formulas = $nf; md5 = $md5; used = $ur.Address() }
    if ($ws.Name -in @("Заявка", "Водитель МГ")) {
      $cells = New-Object System.Collections.Generic.List[object]
      foreach ($c in $ur.Cells) {
        if ($c.MergeCells -and $c.MergeArea.Cells(1,1).Address() -ne $c.Address()) { continue }
        $t = "$($c.Text)"
        if ($t.Trim() -eq "") { continue }
        $cells.Add([ordered]@{ a = $c.Address($false,$false); r = $c.Row; c = $c.Column; t = $t; b = "$($c.Font.Bold)"; f = $c.HasFormula })
      }
      $res.sheets[$ws.Name] = $cells
    }
  }
  $wb.Close($false)
  [IO.File]::WriteAllText($OutJson, ($res | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
} finally { $xl.Quit() }
