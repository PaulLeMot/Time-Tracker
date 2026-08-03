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

def get_today_str() -> str:
    return datetime.now().strftime("%y%m%d")

def get_excel_file_exists() -> bool:
    """Проверяет, существует ли хотя бы один файл *_mp_rep.xlsx за последние 30 дней."""
    base_path = "/work/!МП_(FSk)/!Rep"
    today = datetime.now()
    for days_back in range(0, 31):
        date = today - timedelta(days=days_back)
        date_str = date.strftime("%y%m%d")
        file_name = f"{date_str}_mp_rep.xlsx"
        file_path = os.path.join(base_path, file_name)
        if os.path.exists(file_path):
            return True
    return False

def check_files_status(date_str: str) -> dict:
    """Проверяет наличие необходимых файлов:
       - mp_rep: хотя бы один за последние 30 дней
       - OZ/WB: строго за сегодняшнюю дату
    """
    base_fbs = "/work/!МП_(FSk)/!FBS"
    
    files = {}
    # Проверяем mp_rep (не привязан к дате)
    mp_rep_exists = get_excel_file_exists()
    files["mp_rep.xlsx (любой за 30 дней)"] = mp_rep_exists
    
    # Проверяем OZ и WB за сегодня
    for mk in MARKING_KEYS:
        wb_path = os.path.join(base_fbs, f"{date_str}_FBS", "input", f"{mk}_WB.xlsx")
        oz_path = os.path.join(base_fbs, f"{date_str}_FBS", "input", f"{mk}_OZ.csv")
        files[f"{date_str}_FBS/input/{mk}_WB.xlsx"] = os.path.exists(wb_path)
        files[f"{date_str}_FBS/input/{mk}_OZ.csv"] = os.path.exists(oz_path)
    
    missing = [name for name, exists in files.items() if not exists]
    return {
        "ok": len(missing) == 0,
        "files": files,
        "missing": missing
    }

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
                sticker = str(row.iloc[0]).strip()
                id_val = str(row.iloc[1]).strip()
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
    cache_key = (marking, date_str, "oz")
    if cache_key in _sticker_caches:
        return _sticker_caches[cache_key]["index"]

    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "input", f"{marking}_OZ.csv")
    index = {}
    if os.path.exists(file_path):
        try:
            df = None
            for sep in [';', ',']:
                try:
                    df = pd.read_csv(file_path, header=None, usecols=[1, 15], dtype=str, sep=sep, encoding='utf-8').fillna('')
                    break
                except Exception:
                    continue
            if df is None:
                df = pd.read_csv(file_path, header=None, usecols=[1, 15], dtype=str, sep=None, engine='python', encoding='utf-8').fillna('')
            for _, row in df.iterrows():
                sticker = str(row.iloc[0]).strip()
                art = str(row.iloc[1]).strip()
                if art and art != 'nan' and sticker and sticker != 'nan':
                    if art not in index:
                        index[art] = []
                    index[art].append(sticker)
            print(f"[OZ] Загружен {marking}, индекс: {len(index)} артикулов")
        except Exception as e:
            print(f"Ошибка загрузки OZ-стикеров для {marking}: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[OZ] Файл не найден: {file_path}")
    _sticker_caches[cache_key] = {"index": index}
    return index

def get_oz_qr_index(marking: str, date_str: str):
    cache_key = (marking, date_str, "oz_qr")
    if cache_key in _sticker_caches:
        return _sticker_caches[cache_key].get("qr_index", {})

    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "input", f"{marking}_OZ.csv")
    qr_index = {}

    if os.path.exists(file_path):
        try:
            df = None
            for sep in [';', ',']:
                try:
                    df = pd.read_csv(file_path, header=None, usecols=[15, 30], dtype=str, sep=sep, encoding='utf-8').fillna('')
                    break
                except Exception:
                    continue
            if df is None:
                df = pd.read_csv(file_path, header=None, usecols=[15, 30], dtype=str, sep=None, engine='python', encoding='utf-8').fillna('')
            for _, row in df.iterrows():
                art = str(row.iloc[0]).strip()
                qr = str(row.iloc[1]).strip()
                if art == 'Артикул' or qr == 'Нижний штрихкод':
                    continue
                if art and art != 'nan' and qr and qr != 'nan':
                    qr_index.setdefault(qr, []).append(art)
            print(f"[QR] Загружен индекс для {marking}, записей: {len(qr_index)}")
        except Exception as e:
            print(f"Ошибка загрузки QR-индекса для {marking}: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[QR] Файл не найден: {file_path}")

    if cache_key not in _sticker_caches:
        _sticker_caches[cache_key] = {}
    _sticker_caches[cache_key]["qr_index"] = qr_index
    return qr_index

def get_marking_for_position(col_idx, col_names):
    if col_idx == 0:
        return "FSK", None
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
        return f"{marking_col_name}_WB", False
    elif offset == 6:
        return f"{marking_col_name}_OZ", False
    else:
        return None, None

def get_row_data(row, col_names, code, sticker_indices, oz_sticker_indices, skip_stickers=False, oz_search_art=None):
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
        
        oz_id = row.get(col_names[mk_idx + 4], '').strip() if mk_idx + 4 < len(col_names) else '0'
        oz_bar = row.get(col_names[mk_idx + 6], '').strip() if mk_idx + 6 < len(col_names) else '0'
        oz_id_clean = oz_id if oz_id else '0'
        oz_bar_clean = oz_bar if oz_bar else '0'
        oz_pairs = []
        if not skip_stickers and mk in oz_sticker_indices:
            search_art = oz_search_art if oz_search_art is not None else code
            stickers_for_art = oz_sticker_indices[mk].get(search_art, [])
            if stickers_for_art:
                reverse_index = {}
                for art, st_list in oz_sticker_indices[mk].items():
                    for st in st_list:
                        if st not in reverse_index:
                            reverse_index[st] = []
                        reverse_index[st].append(art)
                for st in stickers_for_art:
                    if st in reverse_index:
                        for art in reverse_index[st]:
                            oz_pairs.append({"sticker": st, "articul": art})
        oz_rows.append({
            "marking": f"{mk}_OZ",
            "platform": "OZ",
            "id": oz_id_clean,
            "bar": oz_bar_clean,
            "stickers": oz_pairs
        })
    
    table.extend(wb_rows)
    table.extend(oz_rows)
    return table

# ========== ЭНДПОИНТЫ (конкретные пути ДО общего параметра) ==========

@router.get("/api/mark/status")
async def get_status():
    today_str = get_today_str()
    status = check_files_status(today_str)
    return {
        "date": today_str,
        "ok": status["ok"],
        "files": status["files"],
        "missing": status["missing"]
    }

@router.post("/api/mark/refresh")
async def refresh_cache():
    today_str = get_today_str()
    status = check_files_status(today_str)
    if not status["ok"]:
        missing_list = "\n".join(status["missing"])
        raise HTTPException(
            status_code=400,
            detail=f"Отсутствуют необходимые файлы:\n{missing_list}"
        )
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

@router.get("/api/mark/{barcode:path}")
async def mark_barcode(barcode: str):
    barcode = barcode.strip()
    if not barcode:
        raise HTTPException(status_code=400, detail="Штрих-код не указан")
    
    normalized = normalize_barcode(barcode)
    if not normalized or len(normalized) < 5:
        raise HTTPException(status_code=400, detail="Некорректный штрих-код")
    
    data, index, col_names, _ = get_cached_data()
    today_str = get_today_str()

    sticker_indices = {}
    for mk in MARKING_KEYS:
        sticker_indices[mk] = get_sticker_index(mk, today_str)

    oz_sticker_indices = {}
    for mk in MARKING_KEYS:
        oz_sticker_indices[mk] = get_oz_sticker_index(mk, today_str)

    qr_markings_map = {}
    found_via_qr = False
    if normalized in index:
        barcodes_to_search = [normalized]
    else:
        qr_index_all = {}
        for mk in MARKING_KEYS:
            qr_idx = get_oz_qr_index(mk, today_str)
            for qr, arts in qr_idx.items():
                qr_index_all.setdefault(qr, []).extend(arts)
                for art in arts:
                    qr_markings_map.setdefault(art, set()).add(mk)

        if barcode in qr_index_all:
            barcodes_to_search = qr_index_all[barcode]
            found_via_qr = True
        else:
            raise HTTPException(status_code=404, detail="Товар не найден")

    all_positions = []
    for bcode in barcodes_to_search:
        if bcode in index:
            all_positions.extend(index[bcode])
    if not all_positions:
        raise HTTPException(status_code=404, detail="Товар не найден")

    products = {}
    for row_idx, col_idx in all_positions:
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
                "qr_markings": set(),
            }

        if code in qr_markings_map:
            products[key]["qr_markings"].update(qr_markings_map[code])

        marking, is_id = get_marking_for_position(col_idx, col_names)
        if marking:
            products[key]["Маркировки"].add(marking)
            products[key]["entries"].append((marking, is_id))
            if marking == "FSK" and not found_via_qr:
                products[key]["skip_stickers"] = True

    for key, data_item in products.items():
        if data_item["skip_stickers"]:
            data_item["sticker_markings"] = set()
            continue

        qr_markings = {f"{mk}_OZ" for mk in data_item["qr_markings"]}
        id_markings = {marking for marking, is_id in data_item["entries"] if is_id is True}
        barcode_markings = {marking for marking, is_id in data_item["entries"] if is_id is False}

        all_markings = set()
        if id_markings:
            all_markings.update(id_markings)
        if barcode_markings:
            all_markings.update(barcode_markings)
        if qr_markings:
            all_markings.update(qr_markings)

        data_item["sticker_markings"] = all_markings

    results = []
    for key, data_item in products.items():
        row_for_table = None
        for row_idx, col_idx in all_positions:
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

@router.get("/mark")
async def mark_page():
    return FileResponse("static/mark.html")