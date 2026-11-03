param([string]$Book, [string]$Out)
# Перекрашивает в стиль «вариант 3» только листы «Заявка» и «Водитель МГ». ТН и формулы не трогает:
# меняются только шрифт, заливка, цвет текста и границы. Сохраняет копию в .xlsx.
$BLUE  = 30 + 111*256 + 224*65536    # 1E6FE0
$DARK  = 11 + 74*256 + 168*65536     # 0B4AA8
$LIGHT = 234 + 242*256 + 254*65536   # EAF2FE
$VAL   = 246 + 249*256 + 254*65536   # F6F9FE
$WHITE = 16777215
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.ScreenUpdating = $false
try {
  $wb = $xl.Workbooks.Open($Book, 0, $true)
  foreach ($name in @("Заявка", "Водитель МГ")) {
    $ws = $wb.Worksheets.Item($name)
    $ur = $ws.UsedRange
    $lastRow = $ur.Row + $ur.Rows.Count - 1; $lastCol = $ur.Column + $ur.Columns.Count - 1
    # строки-ориентиры
    $rowOf = @{}
    foreach ($c in $ur.Cells) {
      $t = "$($c.Text)".Trim()
      if ($t -match '^1\.\s*ЗАГРУЗКА' -and -not $rowOf.form) { $rowOf.form = $c.Row }
      if ($t -match '^10\.\s*Условия' -and -not $rowOf.cond) { $rowOf.cond = $c.Row }
      if ($t -match '^1\.\s*Оригиналы' -and -not $rowOf.legal) { $rowOf.legal = $c.Row }
      if ($t -match '^1[12]\.\s*(Перевозчик|Заказчик|Исполнитель)\s*$' -and -not $rowOf.req) { $rowOf.req = $c.Row }
      if ($t -match '^Договор\s*-\s*заявка' -and -not $rowOf.title) { $rowOf.title = $c.Row }
      if ($t -match '^(С места погрузки|которым заключали)' -and -not $rowOf.condAlt) { $rowOf.condAlt = $c.Row }
    }
    # в шаблонах «со склада» строки «10. Условия перевозки…» удалены — ориентируемся на продолжение текста
    if (-not $rowOf.cond) { $rowOf.cond = $rowOf.condAlt }
    $all = $ws.Range($ws.Cells(1,1), $ws.Cells($lastRow, $lastCol))
    $all.Font.Name = "Arial"
    $all.Font.Color = 0x202020
    if ($rowOf.title) { $tc = $ws.Rows($rowOf.title); $tc.Font.Color = $DARK; $tc.Font.Bold = $true }

    $zones = @()
    if ($rowOf.form -and $rowOf.cond) { $zones += ,@($rowOf.form, ($rowOf.cond - 1)) }
    if ($rowOf.req) { $zones += ,@($rowOf.req, $lastRow) }
    foreach ($z in $zones) {
      $rg = $ws.Range($ws.Cells($z[0],1), $ws.Cells($z[1], $lastCol))
      $rg.Interior.Color = $VAL
      foreach ($b in 7,8,9,10,11,12) { $e = $rg.Borders.Item($b); $e.LineStyle = 1; $e.Weight = -4138; $e.Color = $WHITE }
    }
    # «ОБЯЗАТЕЛЬНОЕ УСЛОВИЕ!» — голубая плашка, тёмно-синий жирный
    if ($rowOf.cond -and $rowOf.legal) {
      $rg = $ws.Range($ws.Cells($rowOf.cond,1), $ws.Cells($rowOf.legal - 1, $lastCol))
      $rg.Interior.Color = $LIGHT; $rg.Font.Color = $DARK; $rg.Font.Bold = $true
    }
    # подписи полей и заголовки разделов
    foreach ($c in $ur.Cells) {
      $t = "$($c.Text)".Trim()
      if ($t -eq "") { continue }
      if ($c.MergeCells -and $c.MergeArea.Cells(1,1).Address() -ne $c.Address()) { continue }
      $ma = $c.MergeArea
      $inForm = ($rowOf.form -and $c.Row -ge $rowOf.form -and $c.Row -lt $rowOf.cond) -or ($rowOf.req -and $c.Row -ge $rowOf.req)
      if (-not $inForm) { continue }
      if ($t.Length -lt 45 -and $t -match '^\d{1,2}\.\s*\D' -and $c.Font.Bold -eq $true) {
        $ma.Interior.Color = $BLUE; $ma.Font.Color = $WHITE; $ma.Font.Bold = $true
      } elseif ($t -match '^\d\.\d\.' -or $t -match '^(Авто|Полуприцеп|Телефон|Контакт)') {
        $ma.Interior.Color = $LIGHT; $ma.Font.Color = $DARK
      }
    }
    if ($rowOf.cond) { $h = $ws.Cells($rowOf.cond, 1).MergeArea; $h.Interior.Color = $BLUE; $h.Font.Color = $WHITE }
    "$name : форма с $($rowOf.form), условие $($rowOf.cond), текст с $($rowOf.legal), реквизиты с $($rowOf.req)"
  }
  $wb.SaveAs($Out, 51)
  $wb.Close($false)
} finally { $xl.ScreenUpdating = $true; $xl.Quit() }
