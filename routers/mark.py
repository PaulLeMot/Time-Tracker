import os
import re
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime, timedelta

router = APIRouter(tags=["mark"])

_cache = {
    "file_path": None,
    "file_mtime": None,
    "data": None,
    "index": None,
    "col_names": None,
    "date_str": None,
}

_sticker_caches = {}

MARKING_KEYS = ["sia", "ktv", "reg", "kpd"]
EXCLUDED_COLUMNS = {12, 15, 19, 22, 26, 29, 33, 36}

def normalize_barcode(barcode: str) -> str:
    barcode = barcode.strip()
    if barcode.startswith("2400000") and len(barcode) == 13:
        return barcode[7:12]
    return barcode

def generate_ean13(code5: str) -> str:
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
    """Загружает WB-стикеры (колонки C и L)"""
    cache_key = (marking, date_str, "wb")
    if cache_key in _sticker_caches:
        return _sticker_caches[cache_key]["index"]

    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "input", f"{marking}_WB.xlsx")
    index = {}
    if os.path.exists(file_path):
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
            print(f"Ошибка загрузки WB-стикеров для {marking}: {e}")
            pass
    _sticker_caches[cache_key] = {"index": index}
    return index

def get_oz_sticker_index(marking: str, date_str: str):
    """Загружает OZ-стикеры (колонки B и P)"""
    cache_key = (marking, date_str, "oz")
    if cache_key in _sticker_caches:
        return _sticker_caches[cache_key]["index"]

    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "input", f"{marking}_OZ.xlsx")
    index = {}
    if os.path.exists(file_path):
        try:
            # B = 1, P = 15
            df = pd.read_excel(file_path, header=None, usecols=[1, 15], dtype=str).fillna('')
            for _, row in df.iterrows():
                sticker = str(row[1]).strip()
                art = str(row[15]).strip()
                if art and art != 'nan' and sticker and sticker != 'nan':
                    if art not in index:
                        index[art] = []
                    index[art].append(sticker)
        except Exception as e:
            print(f"Ошибка загрузки OZ-стикеров для {marking}: {e}")
            pass
    _sticker_caches[cache_key] = {"index": index}
    return index

def get_marking_for_position(col_idx, col_names):
    """Возвращает (marking, is_id) где is_id=True для ID-колонок (offset 1 или 4)"""
    if col_idx == 0:
        return "FSK", None  # None означает, что это не ID и не штрих-код, а колонка A
    marking_col_name = None
    for c in range(col_idx, -1, -1):
        if col_names[c] in MARKING_KEYS:
            marking_col_name = col_names[c]
            break
    if marking_col_name is None:
        return None, None
    offset = col_idx - col_names.index(marking_col_name)
    if offset == 1:
        return f"{marking_col_name}_WB", True
    elif offset == 4:
        return f"{marking_col_name}_OZ", True
    elif offset == 3:
        return f"{marking_col_name}_WB", False  # штрих-код
    elif offset == 6:
        return f"{marking_col_name}_OZ", False
    else:
        return None, None

def get_row_data(row, col_names, code, sticker_indices, oz_sticker_indices, skip_stickers=False):
    """
    Собирает таблицу данных для товара.
    sticker_indices: dict {marking: {id: [стикеры]}} – для WB
    oz_sticker_indices: dict {marking: {артикул: [стикеры]}} – для OZ
    skip_stickers: если True – стикеры не ищем (только для FSK)
    """
    table = []
    
    fsk_bar = generate_ean13(code)
    table.append({
        "marking": "FSK",
        "platform": "FSK",
        "id": code,
        "bar": fsk_bar,
        "stickers": []
    })

    wb_rows = []
    oz_rows = []
    
    for mk in MARKING_KEYS:
        try:
            mk_idx = col_names.index(mk)
        except ValueError:
            continue

        # --- WB ---
        wb_id = row.get(col_names[mk_idx + 1], '').strip() if mk_idx + 1 < len(col_names) else '0'
        wb_bar = row.get(col_names[mk_idx + 3], '').strip() if mk_idx + 3 < len(col_names) else '0'
        wb_id_clean = wb_id if wb_id else '0'
        wb_bar_clean = wb_bar if wb_bar else '0'
        wb_stickers = []
        if not skip_stickers and wb_id_clean != '0' and mk in sticker_indices:
            wb_stickers = sticker_indices[mk].get(wb_id_clean, [])
        wb_rows.append({
            "marking": f"{mk}_WB",
            "platform": "WB",
            "id": wb_id_clean,
            "bar": wb_bar_clean,
            "stickers": wb_stickers
        })
        
        # --- OZ ---
        oz_id = row.get(col_names[mk_idx + 4], '').strip() if mk_idx + 4 < len(col_names) else '0'
        oz_bar = row.get(col_names[mk_idx + 6], '').strip() if mk_idx + 6 < len(col_names) else '0'
        oz_id_clean = oz_id if oz_id else '0'
        oz_bar_clean = oz_bar if oz_bar else '0'
        oz_stickers = []
        if not skip_stickers and mk in oz_sticker_indices:
            # Для OZ используем артикул (код товара) для поиска в 14-й колонке
            oz_stickers = oz_sticker_indices[mk].get(code, [])
        oz_rows.append({
            "marking": f"{mk}_OZ",
            "platform": "OZ",
            "id": oz_id_clean,
            "bar": oz_bar_clean,
            "stickers": oz_stickers
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
    
    data, index, col_names, _ = get_cached_data()
    if normalized not in index:
        raise HTTPException(status_code=404, detail="Товар не найден")

    today_str = datetime.now().strftime("%y%m%d")

    # Загружаем WB-стикеры (для ID-колонок)
    sticker_indices = {}
    for mk in MARKING_KEYS:
        sticker_indices[mk] = get_sticker_index(mk, today_str)

    # Загружаем OZ-стикеры (для артикулов)
    oz_sticker_indices = {}
    for mk in MARKING_KEYS:
        oz_sticker_indices[mk] = get_oz_sticker_index(mk, today_str)

    # Группируем товары
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
                "entries": [],
                "skip_stickers": False,
            }

        marking, is_id = get_marking_for_position(col_idx, col_names)
        if marking:
            products[key]["Маркировки"].add(marking)
            products[key]["entries"].append((marking, is_id))
            if marking == "FSK":
                products[key]["skip_stickers"] = True

    # Определяем маркировки для стикеров (found_markings)
    for key, data_item in products.items():
        if data_item["skip_stickers"]:
            data_item["sticker_markings"] = set()
            continue

        id_markings = {marking for marking, is_id in data_item["entries"] if is_id is True}
        barcode_markings = {marking for marking, is_id in data_item["entries"] if is_id is False}

        if id_markings:
            data_item["sticker_markings"] = id_markings
        else:
            data_item["sticker_markings"] = barcode_markings

    # Формируем результат
    results = []
    for key, data_item in products.items():
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
                oz_sticker_indices,
                skip_stickers=data_item["skip_stickers"]
            )
        else:
            table = []

        found_markings = list(data_item["sticker_markings"])

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

# -------------------------------------------------------------------
# ЭНДПОИНТ ДЛЯ ОБНОВЛЕНИЯ КЭША
# -------------------------------------------------------------------
@router.post("/api/mark/refresh")
async def refresh_cache():
    _cache.update({
        "file_path": None,
        "file_mtime": None,
        "data": None,
        "index": None,
        "col_names": None,
        "date_str": None,
    })
    _sticker_caches.clear()
    return {"message": "Кэш очищен. Данные будут перезагружены при следующем запросе."}

@router.get("/mark")
async def mark_page():
    return FileResponse("static/mark.html")