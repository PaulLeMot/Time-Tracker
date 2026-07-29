import os
import re
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime, timedelta

router = APIRouter(tags=["mark"])

# Кэш для основной таблицы
_cache = {
    "file_path": None,
    "file_mtime": None,
    "data": None,
    "index": None,
    "col_names": None,
    "date_str": None,  # дата в формате YYMMDD (из отчёта)
}

# Кэш для файлов стикеров
_sticker_caches = {}  # ключ: (marking, date_str) -> {"mtime": float, "index": dict}

MARKING_KEYS = ["sia", "ktv", "reg", "kpd"]  # порядок важен
EXCLUDED_COLUMNS = {12, 15, 19, 22, 26, 29, 33, 36}

def normalize_barcode(barcode: str) -> str:
    barcode = barcode.strip()
    if barcode.startswith("2400000") and len(barcode) == 13:
        return barcode[7:12]
    return barcode

def generate_ean13(code5: str) -> str:
    """Генерирует EAN13 вида 2400000XXXXX + контрольная цифра"""
    if not code5 or len(code5) != 5 or not code5.isdigit():
        return "0"
    base = "2400000" + code5
    total = 0
    for i, ch in enumerate(base):
        digit = int(ch)
        if i % 2 == 0:
            total += digit
        else:
            total += digit * 3
    checksum = (10 - (total % 10)) % 10
    return base + str(checksum)

def get_excel_file_path() -> str:
    base_path = "/work/!МП_(FSk)/!Rep"
    today = datetime.now()
    for days_back in range(0, 31):
        date = today - timedelta(days=days_back)
        date_str = date.strftime("%y%m%d")
        file_name = f"{date_str}_mp_rep.xlsx"
        file_path = os.path.join(base_path, file_name)
        if os.path.exists(file_path):
            return file_path
    raise FileNotFoundError(f"Не найдено ни одного файла {base_path}/*_mp_rep.xlsx за последние 30 дней")

def load_excel_data(file_path: str):
    df = pd.read_excel(file_path, sheet_name="ids", usecols="A:AL", dtype=str).fillna('')
    col_names = list(df.columns)
    data = df.to_dict(orient='records')
    index = {}
    for row_idx, row in enumerate(data):
        for col_idx, col_name in enumerate(col_names):
            if col_idx in EXCLUDED_COLUMNS:
                continue
            value = row.get(col_name, '')
            if value and value.strip():
                val = value.strip()
                if val not in index:
                    index[val] = []
                index[val].append((row_idx, col_idx))
    return data, index, col_names

def get_cached_data():
    file_path = get_excel_file_path()
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Файл {file_path} не найден")
    mtime = os.path.getmtime(file_path)
    if (_cache["file_path"] != file_path or 
        _cache["file_mtime"] != mtime or 
        _cache["data"] is None):
        data, index, col_names = load_excel_data(file_path)
        # Извлекаем дату из имени файла (YYMMDD) – используется только для информации
        match = re.search(r'(\d{6})_mp_rep\.xlsx', file_path)
        date_str = match.group(1) if match else None
        _cache.update({
            "file_path": file_path,
            "file_mtime": mtime,
            "data": data,
            "index": index,
            "col_names": col_names,
            "date_str": date_str
        })
    return _cache["data"], _cache["index"], _cache["col_names"], _cache["date_str"]

def get_sticker_index(marking: str, date_str: str):
    """Загружает файл стикеров для маркировки и возвращает словарь id -> список стикеров."""
    cache_key = (marking, date_str)
    if cache_key in _sticker_caches:
        # можно проверить mtime, но для простоты пока пропустим
        return _sticker_caches[cache_key]["index"]

    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "input", f"{marking}_WB.xlsx")
    index = {}
    if os.path.exists(file_path):
        # Читаем колонки C (стикер) и L (ID) без заголовков
        try:
            df = pd.read_excel(file_path, header=None, usecols=[2, 11], dtype=str).fillna('')
            for _, row in df.iterrows():
                sticker = str(row[2]).strip()
                id_val = str(row[11]).strip()
                if id_val and id_val != 'nan' and sticker and sticker != 'nan':
                    if id_val not in index:
                        index[id_val] = []
                    index[id_val].append(sticker)
        except Exception as e:
            # Если файл повреждён или не читается, просто возвращаем пустой индекс
            print(f"Ошибка загрузки стикеров для {marking}: {e}")
            pass
    _sticker_caches[cache_key] = {"index": index}
    return index

def get_marking_for_position(row, col_idx, col_names) -> str:
    if col_idx == 0:
        return "FSK"
    marking_col_idx = None
    marking_col_name = None
    for c in range(col_idx, -1, -1):
        if col_names[c] in MARKING_KEYS:
            marking_col_idx = c
            marking_col_name = col_names[c]
            break
    if marking_col_name is None:
        return None
    offset = col_idx - marking_col_idx
    if offset in (1, 3):
        platform = "WB"
    elif offset in (4, 6):
        platform = "OZ"
    else:
        return None
    return f"{marking_col_name}_{platform}"

def get_row_data(row, col_names, code, sticker_indices, skip_stickers=False):
    """
    Собирает таблицу данных для товара.
    sticker_indices: dict {marking: dict {id: [sticker1, sticker2, ...]}}
    skip_stickers: если True, то для всех WB-строк стикеры не ищутся
    """
    table = []
    
    # FSK (МП)
    fsk_bar = generate_ean13(code)
    table.append({
        "marking": "FSK",
        "platform": "FSK",
        "id": code,
        "bar": fsk_bar,
        "stickers": []  # для FSK стикеров нет
    })

    wb_rows = []
    oz_rows = []
    
    for mk in MARKING_KEYS:
        try:
            mk_idx = col_names.index(mk)
        except ValueError:
            continue
        # WB
        wb_id = row.get(col_names[mk_idx + 1], '').strip() if mk_idx + 1 < len(col_names) else '0'
        wb_bar = row.get(col_names[mk_idx + 3], '').strip() if mk_idx + 3 < len(col_names) else '0'
        wb_id_clean = wb_id if wb_id else '0'
        wb_bar_clean = wb_bar if wb_bar else '0'
        # Получаем стикеры только если не skip_stickers
        stickers = []
        if not skip_stickers and wb_id_clean != '0' and mk in sticker_indices:
            stickers = sticker_indices[mk].get(wb_id_clean, [])
        wb_rows.append({
            "marking": f"{mk}_WB",
            "platform": "WB",
            "id": wb_id_clean,
            "bar": wb_bar_clean,
            "stickers": stickers
        })
        
        # OZ
        oz_id = row.get(col_names[mk_idx + 4], '').strip() if mk_idx + 4 < len(col_names) else '0'
        oz_bar = row.get(col_names[mk_idx + 6], '').strip() if mk_idx + 6 < len(col_names) else '0'
        oz_id_clean = oz_id if oz_id else '0'
        oz_bar_clean = oz_bar if oz_bar else '0'
        oz_rows.append({
            "marking": f"{mk}_OZ",
            "platform": "OZ",
            "id": oz_id_clean,
            "bar": oz_bar_clean,
            "stickers": []  # для OZ стикеров пока нет (путь MP_WB.xlsx только для WB)
        })
    
    table.extend(wb_rows)
    table.extend(oz_rows)
    
    return table

@router.get("/api/mark/{barcode:path}")
async def mark_barcode(barcode: str):
    barcode = barcode.strip()
    if not barcode:
        raise HTTPException(status_code=400, detail="Штрих-код не указан")
    
    normalized = normalize_barcode(barcode)
    if not normalized or len(normalized) < 5:
        raise HTTPException(status_code=400, detail="Некорректный штрих-код")
    
    data, index, col_names, _ = get_cached_data()  # игнорируем date_str из кэша
    if normalized not in index:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Всегда используем сегодняшнюю дату для стикеров
    today_str = datetime.now().strftime("%y%m%d")

    # Загружаем стикеры для всех маркировок (только WB) с сегодняшней датой
    sticker_indices = {}
    for mk in MARKING_KEYS:
        sticker_indices[mk] = get_sticker_index(mk, today_str)

    products = {}

    for row_idx, col_idx in index[normalized]:
        row = data[row_idx]
        code = row.get("Код", "")
        view = row.get("Вид товара", "")
        fandom = row.get("Фандом", "") or row.get("Фандом 4ek", "")
        name = row.get("Название", "")
        key = (code, view, fandom, name)

        if key not in products:
            products[key] = {
                "Код": code,
                "Вид": view,
                "Фандом": fandom,
                "Название": name,
                "Маркировки": set(),
                "skip_stickers": False   # по умолчанию не пропускаем стикеры
            }

        # Если текущее вхождение найдено по столбцу A (col_idx == 0)
        if col_idx == 0:
            products[key]["skip_stickers"] = True

        marking = get_marking_for_position(row, col_idx, col_names)
        if marking:
            products[key]["Маркировки"].add(marking)

    results = []
    for key, data_item in products.items():
        # Собираем таблицу для первого вхождения (берем первую строку с таким кодом)
        row_for_table = None
        for row_idx, col_idx in index[normalized]:
            if data_item["Код"] == data[row_idx].get("Код", ""):
                row_for_table = data[row_idx]
                break
        if row_for_table is not None:
            table = get_row_data(
                row_for_table,
                col_names,
                data_item["Код"],
                sticker_indices,
                skip_stickers=data_item.get("skip_stickers", False)
            )
        else:
            table = []
        
        found_markings = list(data_item["Маркировки"]) if data_item["Маркировки"] else []
        
        item = {
            "Код": data_item["Код"],
            "Вид": data_item["Вид"],
            "Фандом": data_item["Фандом"],
            "Название": data_item["Название"],
            "Маркировка": ", ".join(sorted(data_item["Маркировки"])) if data_item["Маркировки"] else None,
            "found_markings": found_markings,
            "table": table
        }
        results.append(item)

    if not results:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    return results

@router.get("/mark")
async def mark_page():
    return FileResponse("static/mark.html")