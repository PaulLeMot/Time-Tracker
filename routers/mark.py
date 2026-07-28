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
}

def get_excel_file_path() -> str:
    today = datetime.now().strftime("%y%m%d")
    base_path = "/work/!МП_(FSk)/!Rep"
    return os.path.join(base_path, f"{today}_mp_rep.xlsx")

def load_excel_data(file_path: str):
    # Читаем конкретный лист "ids"
    df = pd.read_excel(file_path, sheet_name="ids", dtype=str).fillna('')
    data = df.to_dict(orient='records')
    index = {}
    for idx, row in enumerate(data):
        for col, value in row.items():
            if value and value.strip():
                val = value.strip()
                if val not in index:
                    index[val] = []
                if idx not in index[val]:
                    index[val].append(idx)
    return data, index

def get_cached_data():
    file_path = get_excel_file_path()
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Файл {file_path} не найден")
    mtime = os.path.getmtime(file_path)
    if (_cache["file_path"] != file_path or 
        _cache["file_mtime"] != mtime or 
        _cache["data"] is None):
        data, index = load_excel_data(file_path)
        _cache.update({"file_path": file_path, "file_mtime": mtime, "data": data, "index": index})
    return _cache["data"], _cache["index"]

@router.get("/api/mark/{barcode:path}")
async def mark_barcode(barcode: str):
    barcode = barcode.strip()
    if not barcode:
        raise HTTPException(status_code=400, detail="Штрих-код не указан")
    data, index = get_cached_data()
    if barcode not in index:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return [data[idx] for idx in index[barcode]]

@router.get("/mark")
async def mark_page():
    return FileResponse("static/mark.html")