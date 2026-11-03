"""Достаёт текст из старых Excel (.xls), чтобы поиск файлов искал и внутри них.

    python tools/read_xls.py

Библиотеки для .xls не установлены, поэтому через сам Excel: он открывает файл только для чтения
(макросы выключены), сохраняет копию .xlsx во временную папку, текст читается из копии, копия удаляется.
Результат — %USERPROFILE%\\vl_find_files\\xls.json; готовое (тот же размер и дата файла) не пересчитывает.
"""
import os, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_files as ff  # noqa: E402

LOG = os.path.join(os.path.dirname(ff.XLS_CACHE), 'ocr_log.txt')

PS = r'''
$ErrorActionPreference = 'Continue'
$jobs = Get-Content -LiteralPath $args[0] -Encoding UTF8
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false
$xl.DisplayAlerts = $false
$xl.AutomationSecurity = 3
$m = [Type]::Missing
$out = New-Object System.Collections.Generic.List[string]
foreach ($line in $jobs) {
    $src, $dst = $line -split '\|', 2
    try {
        # пароль-заглушка: защищённый файл не спросит пароль, а просто не откроется
        $wb = $xl.Workbooks.Open($src, 0, $true, $m, 'nopass', 'nopass', $true)
        $wb.SaveAs($dst, 51)
        $wb.Close($false)
        $out.Add("ok|$src")
    } catch {
        $out.Add("err|$src|" + $_.Exception.Message)
    }
}
$xl.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null
$out | Set-Content -LiteralPath $args[1] -Encoding UTF8
'''


def log(msg):
    line = time.strftime('%H:%M:%S ') + msg
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def main():
    os.makedirs(os.path.dirname(ff.XLS_CACHE), exist_ok=True)
    cache = ff.load_cache(ff.XLS_CACHE)
    todo = []
    for path in ff.iter_files(ff.DEFAULT_ROOTS):
        if not path.lower().endswith('.xls'):
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        key, stamp = os.path.normcase(path), f'{st.st_size}:{int(st.st_mtime)}'
        e = cache.get(key)
        if not e or e[0] != stamp:
            todo.append((key, path, stamp))
    log(f'Старые Excel (.xls): прочитать {len(todo)}')
    if not todo:
        return
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix='vl_xls_') as tmp:
        jobs = {os.path.join(tmp, f'{i}.xlsx'): t for i, t in enumerate(todo)}
        lst, res, ps1 = (os.path.join(tmp, n) for n in ('jobs.txt', 'result.txt', 'conv.ps1'))
        with open(lst, 'w', encoding='utf-8-sig') as f:
            f.write('\n'.join(f'{path}|{dst}' for dst, (key, path, stamp) in jobs.items()))
        with open(ps1, 'w', encoding='utf-8-sig') as f:
            f.write(PS)
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1, lst, res],
                       timeout=3600)
        errors = 0
        try:
            with open(res, encoding='utf-8-sig') as f:
                for line in f:
                    if line.startswith('err|'):
                        errors += 1
                        log('  не открылся: ' + os.path.basename(line.split('|')[1]))
        except OSError:
            pass
        for dst, (key, path, stamp) in jobs.items():
            if os.path.exists(dst):
                cache[key] = [stamp, ' '.join(ff.words(ff.read_text(dst, '.xlsx')))[:ff.MAX_TEXT]]
    ff.save_cache(cache, ff.XLS_CACHE)
    log(f'Старые Excel: готово за {(time.time() - t0) / 60:.1f} мин, не открылось: {errors}')


if __name__ == '__main__':
    main()
