param([string]$Donor, [string]$Target)
# Копирует строки «10. Условия перевозки: ОБЯЗАТЕЛЬНОЕ УСЛОВИЕ!» и «С места погрузки…» с листа «Заявка» книги-донора
# и вставляет их в лист «Заявка» целевой книги перед строкой «которым заключали заявку…». Excel сам сдвигает ссылки формул.
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
try {
  $src = $xl.Workbooks.Open($Donor, 0, $true)
  $dst = $xl.Workbooks.Open($Target, 0, $false)
  $ws = $src.Worksheets.Item("Заявка"); $wt = $dst.Worksheets.Item("Заявка")
  $r1 = $ws.Range("A1:A80").Find("10. Условия перевозки").Row
  $rt = $wt.Range("A1:A80").Find("которым заключали").Row
  if ($wt.Range("A1:A80").Find("10. Условия перевозки")) { "уже есть — пропуск"; return }
  $ws.Rows("$($r1):$($r1 + 1)").Copy() | Out-Null
  $wt.Rows("$rt").Insert(-4121) | Out-Null
  "вставлено в строки $rt-$($rt + 1): " + $wt.Cells($rt,1).Text + " | " + $wt.Cells($rt + 1,1).Text
  $dst.Save()
  $src.Close($false); $dst.Close($false)
} finally { $xl.Quit() }
