import os
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime

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
    Преобразует локальный EAN13 (формат 2000000NNNNNX) в код товара NNNNN.
    Если штрих-код не соответствует формату, возвращает его без изменений.
    """
    barcode = barcode.strip()
    if barcode.startswith("2000000") and len(barcode) == 13:
        return barcode[7:12]  # берём 5 цифр
    return barcode

def get_excel_file_path() -> str:
    today = datetime.now().strftime("%y%m%d")
    base_path = "/work/!МП_(FSk)/!Rep"
    return os.path.join(base_path, f"{today}_mp_rep.xlsx")

def load_excel_data(file_path: str):
    # Загружаем колонки от A до AL
    df = pd.read_excel(file_path, sheet_name="ids", usecols="A:AL", dtype=str).fillna('')
    col_names = list(df.columns)
    data = df.to_dict(orient='records')
    index = {}
    for row_idx, row in enumerate(data):
        for col_idx, col_name in enumerate(col_names):
            # Пропускаем исключённые колонки
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

    results = []
    for row_idx, col_idx in index[normalized]:
        row = data[row_idx]
        # Идём влево до первой колонки-маркировки
        marking_col = None
        for c in range(col_idx, -1, -1):
            if col_names[c] in MARKING_KEYS:
                marking_col = col_names[c]
                break
        marking_value = marking_col if marking_col else ''
        if not marking_value:
            continue
        item = {
            "Код": row.get("Код", ""),
            "Вид": row.get("Вид товара", ""),
            "Фандом": row.get("Фандом", "") or row.get("Фандом 4ek", ""),
            "Название": row.get("Название", ""),
            "Маркировка": marking_value
        }
        results.append(item)
    
    if not results:
        raise HTTPException(status_code=404, detail="Товар не найден (нет маркировки)")
    
    return results

@router.get("/mark")
async def mark_page():
    return FileResponse("static/mark.html") 