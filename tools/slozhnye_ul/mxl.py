# Чтение табличного документа 1С (.mxl, текстовый формат «MOXCEL» со скобками) в словарь {(строка, колонка): текст}.
import re

TOK = re.compile(r'"((?:[^"]|"")*)"|([{},])|([^{},"\s]+)', re.S)


def _tree(data):
    stack, cur = [], []
    for m in TOK.finditer(data):
        s, p, bare = m.groups()
        if s is not None:
            cur.append(s.replace('""', '"'))
        elif p == '{':
            stack.append(cur); cur = []
        elif p == '}':
            done = cur; cur = stack.pop(); cur.append(done)
        elif bare is not None:
            cur.append(int(bare) if bare.lstrip('-').isdigit() else bare)
    return cur


def _text(cell):
    # ячейка: [формат, ..., [1,1,["#", текст]], 0]; пустая — [формат, [1,0], 0]
    for x in cell:
        if isinstance(x, list) and len(x) >= 3 and x[:2] == [1, 1] and isinstance(x[2], list) and x[2][:1] == ['#']:
            return x[2][1] if len(x[2]) > 1 and isinstance(x[2][1], str) else ''
    return None


def _rows(lst):
    # плоский список строк: номер, формат строки (0 или №), число ячеек, (колонка, ячейка)×n, ...
    out, i = {}, 0
    while i + 2 < len(lst):
        r, z, n = lst[i], lst[i + 1], lst[i + 2]
        if not (isinstance(r, int) and isinstance(z, int) and isinstance(n, int) and n >= 0):
            return out
        j = i + 3
        for _ in range(n):
            if j + 1 >= len(lst) or not isinstance(lst[j], int) or not isinstance(lst[j + 1], list):
                return out
            t = _text(lst[j + 1])
            if t:
                out[(r, lst[j])] = t.strip()
            j += 2
        i = j
    return out


def read(path):
    data = open(path, 'rb').read()
    data = data[data.index(b'{'):].decode('utf-8-sig', 'replace')
    best = {}

    def walk(node):
        nonlocal best
        if not isinstance(node, list):
            return
        for k in range(min(len(node), 30)):
            if isinstance(node[k], int):
                res = _rows(node[k:])
                if res and len(res) > len(best):
                    best = res
        for x in node:
            walk(x)
    walk(_tree(data))
    return best
