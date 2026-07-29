import os
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
}

MARKING_KEYS = {"sia", "ktv", "reg", "kpd"}

# Индексы колонок, которые нужно исключить из поиска (0-based, A=0)
# M=12, P=15, T=19, W=22, AA=26, AD=29, AH=33, AK=36
EXCLUDED_COLUMNS = {12, 15, 19, 22, 26, 29, 33, 36}

def normalize_barcode(barcode: str) -> str:
    """
    Преобразует локальный EAN13 (формат 2400000NNNNNX) в код товара NNNNN.
    Если штрих-код не соответствует формату, возвращает его без изменений.
    """
    barcode = barcode.strip()
    if barcode.startswith("2400000") and len(barcode) == 13:
        return barcode[7:12]  # берём 5 цифр
    return barcode

def get_excel_file_path() -> str:
    """
    Возвращает путь к самому свежему файлу с отчётом.
    Ищет файл за сегодня, если нет – за вчера и т.д., вплоть до 30 дней назад.
    """
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
        _cache.update({
            "file_path": file_path,
            "file_mtime": mtime,
            "data": data,
            "index": index,
            "col_names": col_names
        })
    return _cache["data"], _cache["index"], _cache["col_names"]

def get_marking_for_position(row, col_idx, col_names) -> str:
    """
    Определяет маркировку для найденного кода по индексу колонки.
    Если код найден в колонке A (индекс 0) – возвращает "FSK".
    Иначе ищет маркировку (sia/ktv/reg/kpd) слева, затем определяет площадку (WB/OZ)
    по смещению относительно колонки маркировки.
    Возвращает строку вида "маркировка_площадка" или "маркировка" если площадка не определена.
    """
    # Если колонка A – особый случай
    if col_idx == 0:
        return "FSK"
    
    # Ищем маркировку слева
    marking_col_name = None
    marking_col_idx = None
    for c in range(col_idx, -1, -1):
        if col_names[c] in MARKING_KEYS:
            marking_col_name = col_names[c]
            marking_col_idx = c
            break
    
    if not marking_col_name:
        return None  # маркировка не найдена
    
    # Определяем площадку по смещению
    offset = col_idx - marking_col_idx
    # Ожидаемые смещения: 1=WB_id, 2=WB_art, 3=WB_bar, 4=OZ_id, 5=OZ_sku, 6=OZ_bar
    if offset in (1, 3):
        platform = "WB"
    elif offset in (4, 6):
        platform = "OZ"
    else:
        # Неизвестное смещение – возможно, это сама колонка маркировки (но там не может быть штрих-кода)
        return None
    
    return f"{marking_col_name}_{platform}"

@router.get("/api/mark/{barcode:path}")
async def mark_barcode(barcode: str):
    barcode = barcode.strip()
    if not barcode:
        raise HTTPException(status_code=400, detail="Штрих-код не указан")
    
    normalized = normalize_barcode(barcode)
    if not normalized or len(normalized) < 5:
        raise HTTPException(status_code=400, detail="Некорректный штрих-код")
    
    data, index, col_names = get_cached_data()
    if normalized not in index:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Группировка товаров по основным полям
    products = {}  # ключ: (код, вид, фандом, название) -> данные с множеством маркировок

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
                "Маркировки": set()
            }

        # Определяем маркировку для данного вхождения
        marking = get_marking_for_position(row, col_idx, col_names)
        if marking:
            products[key]["Маркировки"].add(marking)

    # Преобразуем в список результатов
    results = []
    for key, data_item in products.items():
        item = {
            "Код": data_item["Код"],
            "Вид": data_item["Вид"],
            "Фандом": data_item["Фандом"],
            "Название": data_item["Название"],
        }
        if data_item["Маркировки"]:
            item["Маркировка"] = ", ".join(sorted(data_item["Маркировки"]))
        results.append(item)

    if not results:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    return results

@router.get("/mark")
async def mark_page():
    return FileResponse("static/mark.html")