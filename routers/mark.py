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
_reverse_sticker_cache = {}   # новый кэш для обратного индекса по последним 4 цифрам

MARKING_KEYS = ["sia", "ktv", "reg", "kpd"]
EXCLUDED_COLUMNS = {12, 15, 19, 22, 26, 29, 33, 36}

def get_today_str() -> str:
    return datetime.now().strftime("%y%m%d")

def get_excel_file_exists() -> bool:
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
    base_fbs = "/work/!МП_(FSk)/!FBS"
    files = {}
    mp_rep_exists = get_excel_file_exists()
    files["mp_rep.xlsx (любой за 30 дней)"] = mp_rep_exists
    for mk in MARKING_KEYS:
        wb_path = os.path.join(base_fbs, f"{date_str}_FBS", "input", f"{mk}_WB.xlsx")
        oz_path = os.path.join(base_fbs, f"{date_str}_FBS", "input", f"{mk}_OZ.csv")
        files[f"{date_str}_FBS/input/{mk}_WB.xlsx"] = os.path.exists(wb_path)
        files[f"{date_str}_FBS/input/{mk}_OZ.csv"] = os.path.exists(oz_path)
        list_wb_path = os.path.join(base_fbs, f"{date_str}_FBS", "list", f"{mk}_WB.xlsx")
        files[f"{date_str}_FBS/list/{mk}_WB.xlsx"] = os.path.exists(list_wb_path)
    missing = [name for name, exists in files.items() if not exists]
    return {"ok": len(missing) == 0, "files": files, "missing": missing}

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

def get_oz_qr_to_sticker_art_index(marking: str, date_str: str):
    """
    Возвращает словарь: QR-код (нижний штрихкод) -> список (стикер, артикул)
    """
    cache_key = (marking, date_str, "qr_to_sticker_art")
    if cache_key in _sticker_caches:
        return _sticker_caches[cache_key].get("qr_to_sticker_art", {})

    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "input", f"{marking}_OZ.csv")
    qr_to_sticker_art = {}

    if os.path.exists(file_path):
        try:
            df = None
            for sep in [';', ',']:
                try:
                    # Читаем колонки: B (стикер = номер отправления), P (артикул), AE (нижний штрихкод)
                    df = pd.read_csv(file_path, header=None, usecols=[1, 15, 30], dtype=str, sep=sep, encoding='utf-8').fillna('')
                    break
                except Exception:
                    continue
            if df is None:
                df = pd.read_csv(file_path, header=None, usecols=[1, 15, 30], dtype=str, sep=None, engine='python', encoding='utf-8').fillna('')
            for _, row in df.iterrows():
                sticker = str(row.iloc[0]).strip()   # Номер отправления (стикер)
                art = str(row.iloc[1]).strip()        # Артикул
                qr = str(row.iloc[2]).strip()         # Нижний штрихкод
                if sticker == 'Номер отправления' or qr == 'Нижний штрихкод':
                    continue
                if sticker and sticker != 'nan' and art and art != 'nan' and qr and qr != 'nan':
                    if qr not in qr_to_sticker_art:
                        qr_to_sticker_art[qr] = []
                    qr_to_sticker_art[qr].append({
                        "sticker": sticker,
                        "art": art,
                        "marking": marking
                    })
            print(f"[QR-STICKER-ART] Загружен {marking}, записей: {len(qr_to_sticker_art)}")
        except Exception as e:
            print(f"Ошибка загрузки QR->стикер-артикул для {marking}: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[QR-STICKER-ART] Файл не найден: {file_path}")

    if cache_key not in _sticker_caches:
        _sticker_caches[cache_key] = {}
    _sticker_caches[cache_key]["qr_to_sticker_art"] = qr_to_sticker_art
    return qr_to_sticker_art

def get_list_wb_row(marking: str, date_str: str, sticker: str) -> int | None:
    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "list", f"{marking}_WB.xlsx")
    if not os.path.exists(file_path):
        return None

    try:
        header_df = pd.read_excel(file_path, header=None, skiprows=4, nrows=1, dtype=str).fillna('')
        sticker_col_idx = None
        for idx, val in enumerate(header_df.iloc[0]):
            if str(val).strip() == 'Стикер':
                sticker_col_idx = idx
                break
        if sticker_col_idx is None:
            for idx in [6, 5]:
                try:
                    if idx < len(header_df.iloc[0]):
                        sticker_col_idx = idx
                        break
                except:
                    pass
        if sticker_col_idx is None:
            return None

        df = pd.read_excel(file_path, header=None, usecols=[sticker_col_idx], dtype=str).fillna('')
        df = df.iloc[5:].reset_index(drop=True)

        clean_sticker = sticker.replace(' ', '')
        for idx, value in enumerate(df.iloc[:, 0]):
            clean_value = str(value).replace(' ', '')
            if clean_value == clean_sticker:
                return idx + 1
    except Exception as e:
        print(f"[LIST] Ошибка: {e}")
        return None
    return None

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

def get_row_data(row, col_names, code, sticker_indices, oz_sticker_indices, skip_stickers=False, oz_search_art=None, oz_sticker_art_pairs=None):
    """
    oz_sticker_art_pairs: список кортежей (стикер, артикул) для фильтрации OZ-строк
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

        wb_id = row.get(col_names[mk_idx + 1], '').strip() if mk_idx + 1 < len(col_names) else '0'
        wb_bar = row.get(col_names[mk_idx + 3], '').strip() if mk_idx + 3 < len(col_names) else '0'
        wb_id_clean = wb_id if wb_id else '0'
        wb_bar_clean = wb_bar if wb_bar else '0'
        wb_stickers = []
        sticker_to_articul = {}   # новый словарь
        if not skip_stickers and wb_id_clean != '0' and mk in sticker_indices:
            for st in sticker_indices[mk].get(wb_id_clean, []):
                wb_stickers.append(st)
                sticker_to_articul[st] = wb_id_clean   # сопоставляем стикер -> артикул
        wb_rows.append({
            "marking": f"{mk}_WB",
            "platform": "WB",
            "id": wb_id_clean,
            "bar": wb_bar_clean,
            "stickers": wb_stickers,
            "sticker_to_articul": sticker_to_articul   # добавили поле
        })
        
        oz_id = row.get(col_names[mk_idx + 4], '').strip() if mk_idx + 4 < len(col_names) else '0'
        oz_bar = row.get(col_names[mk_idx + 6], '').strip() if mk_idx + 6 < len(col_names) else '0'
        oz_id_clean = oz_id if oz_id else '0'
        oz_bar_clean = oz_bar if oz_bar else '0'
        oz_pairs = []
        if not skip_stickers:
            if oz_sticker_art_pairs is not None:
                for sticker, art, marking in oz_sticker_art_pairs:
                    if marking == mk:
                        oz_pairs.append({"sticker": sticker, "articul": art})
            else:
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

# ========== НОВАЯ ФУНКЦИЯ ДЛЯ ОБРАТНОГО ИНДЕКСА ПО ПОСЛЕДНИМ 4 ЦИФРАМ ==========
def get_reverse_sticker_index(marking: str, date_str: str):
    """
    Возвращает словарь: последние 4 цифры стикера (без пробелов) -> список (id, sticker)
    для указанной марки WB.
    """
    cache_key = (marking, date_str, "reverse_wb")
    if cache_key in _reverse_sticker_cache:
        return _reverse_sticker_cache[cache_key]

    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "input", f"{marking}_WB.xlsx")
    reverse_idx = {}

    if os.path.exists(file_path):
        try:
            df = pd.read_excel(file_path, header=None, usecols=[2, 11], dtype=str).fillna('')
            for _, row in df.iterrows():
                sticker = str(row.iloc[0]).strip()
                id_val = str(row.iloc[1]).strip()
                if not id_val or id_val == 'nan' or not sticker or sticker == 'nan':
                    continue
                clean_sticker = sticker.replace(' ', '')
                if len(clean_sticker) >= 4:
                    last4 = clean_sticker[-4:]
                    if last4 not in reverse_idx:
                        reverse_idx[last4] = []
                    reverse_idx[last4].append((id_val, sticker))
        except Exception as e:
            print(f"Ошибка загрузки обратного индекса для {marking}: {e}")

    _reverse_sticker_cache[cache_key] = reverse_idx
    return reverse_idx

# ========== ЭНДПОИНТЫ ==========

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
    _reverse_sticker_cache.clear()
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

    found_via_qr = False
    found_via_fsk = False

    # Определяем, был ли введён FSK-штрихкод (начинается с 2400000 и длина 13)
    if barcode.startswith("2400000") and len(barcode) == 13:
        found_via_fsk = True

    # Если штрих-код есть в основном индексе (артикул или FSK) — ищем по нему
    if normalized in index:
        all_positions = []
        for pos in index[normalized]:
            all_positions.append((pos[0], pos[1], normalized))
        all_positions = list(set(all_positions))
        if not all_positions:
            raise HTTPException(status_code=404, detail="Товар не найден")
        found_via_qr = False
        qr_art_markings = {}
        sticker_art_pairs = []  # для этого случая не нужны
    else:
        # Поиск по QR-коду для OZ
        qr_to_sticker_art_all = {}
        for mk in MARKING_KEYS:
            qr_data = get_oz_qr_to_sticker_art_index(mk, today_str)
            for qr, items in qr_data.items():
                if qr not in qr_to_sticker_art_all:
                    qr_to_sticker_art_all[qr] = []
                qr_to_sticker_art_all[qr].extend(items)

        if barcode not in qr_to_sticker_art_all:
            raise HTTPException(status_code=404, detail="QR-код не найден в файлах OZ")

        found_via_qr = True
        qr_items = qr_to_sticker_art_all[barcode]  # список {sticker, art, marking}

        # Собираем уникальные пары (стикер, артикул, маркетплейс)
        sticker_art_pairs = set()
        for item in qr_items:
            sticker_art_pairs.add((item["sticker"], item["art"], item["marking"]))
        sticker_art_pairs = list(sticker_art_pairs)

        # Строим словарь артикул -> множество маркировок
        qr_art_markings = {}
        for item in qr_items:
            qr_art_markings.setdefault(item["art"], set()).add(item["marking"])
        
        # Собираем артикулы для поиска
        barcodes_to_search = list(set(item["art"] for item in qr_items))

        # Ищем все позиции в основной таблице по этим артикулам
        all_positions = []
        for bcode in barcodes_to_search:
            if bcode in index:
                for pos in index[bcode]:
                    all_positions.append((pos[0], pos[1], bcode))
        all_positions = list(set(all_positions))
        if not all_positions:
            raise HTTPException(status_code=404, detail="Товар не найден")

    # Группируем по полному ключу (как было)
    products = {}
    for row_idx, col_idx, art in all_positions:
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
                "sticker_art_pairs": [],  # список пар (стикер, артикул, маркетплейс) для этого продукта
            }

        # Добавляем маркировки из QR, если артикул совпадает
        if found_via_qr and code in qr_art_markings:
            products[key]["qr_markings"].update(qr_art_markings[code])
            # Добавляем все пары, где артикул совпадает с code
            for sticker, art, marking in sticker_art_pairs:
                if art == code:
                    products[key]["sticker_art_pairs"].append((sticker, art, marking))

        marking, is_id = get_marking_for_position(col_idx, col_names)
        if marking:
            if marking == "FSK" and found_via_fsk:
                products[key]["skip_stickers"] = True
            else:
                products[key]["Маркировки"].add(marking)
                products[key]["entries"].append((marking, is_id))

    # ---- ВЫЧИСЛЯЕМ sticker_markings ДЛЯ ВСЕХ ПРОДУКТОВ (первый раз) ----
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

    # ---- ПЕРВЫЙ ПРОХОД: строим результаты для исходных продуктов ----
    results = []
    for key, data_item in products.items():
        row_for_table = None
        for row_idx, col_idx, _ in all_positions:
            if data_item["Код"] == data[row_idx].get("Код", ""):
                row_for_table = data[row_idx]
                break
        if row_for_table is not None:
            oz_pairs = data_item["sticker_art_pairs"] if found_via_qr and data_item["sticker_art_pairs"] else None
            table = get_row_data(
                row_for_table,
                col_names,
                data_item["Код"],
                sticker_indices,
                oz_sticker_indices,
                skip_stickers=data_item["skip_stickers"],
                oz_search_art=None,
                oz_sticker_art_pairs=oz_pairs
            )
        else:
            table = []

        # Обогащение WB-стикеров номерами строк из list
        if table:
            for row in table:
                if row.get("platform") == "WB" and row.get("stickers"):
                    new_stickers = []
                    for st in row["stickers"]:
                        if isinstance(st, str):
                            row_num = get_list_wb_row(
                                row["marking"].split('_')[0] if '_' in row["marking"] else "",
                                today_str,
                                st
                            )
                            new_stickers.append({"sticker": st, "row": row_num if row_num is not None else None})
                        else:
                            new_stickers.append(st)
                    row["stickers"] = new_stickers

        found_markings = list(data_item["sticker_markings"])

        if found_via_qr and data_item["qr_markings"]:
            display_marking = ", ".join(sorted(f"{mk}_OZ" for mk in data_item["qr_markings"]))
        else:
            display_marking = ", ".join(sorted(data_item["Маркировки"])) if data_item["Маркировки"] else None

        item = {
            "Код": data_item["Код"],
            "Вид": data_item["Вид"],
            "Фандом": data_item["Фандом"],
            "Название": data_item["Название"],
            "Маркировка": display_marking,
            "found_markings": found_markings,
            "table": table
        }
        results.append(item)

    # ---- ДОБАВЛЯЕМ ПОИСК ДОПОЛНИТЕЛЬНЫХ ТОВАРОВ ПО ОДИНАКОВЫМ ПОСЛЕДНИМ 4 ЦИФРАМ СТИКЕРОВ (В ТОМ ЖЕ WB-ФАЙЛЕ) ----
    additional_ids = set()
    # Проходим по уже построенным результатам, собираем WB-стикеры и их марки
    for item in results:
        for row in item["table"]:
            if row.get("platform") == "WB" and row.get("stickers"):
                marking_full = row["marking"]  # например "sia_WB"
                mark = marking_full.split('_')[0]  # "sia"
                if mark not in MARKING_KEYS:
                    continue
                # Получаем обратный индекс для этой марки
                reverse_idx = get_reverse_sticker_index(mark, today_str)
                for st_obj in row["stickers"]:
                    sticker_str = st_obj["sticker"] if isinstance(st_obj, dict) else st_obj
                    clean = sticker_str.replace(' ', '')
                    if len(clean) >= 4:
                        last4 = clean[-4:]
                        if last4 in reverse_idx:
                            # Находим все id, которые есть в этом индексе
                            for id_val, _ in reverse_idx[last4]:
                                # Проверяем, не является ли этот id уже имеющимся продуктом
                                if id_val not in {p["Код"] for p in products.values()}:
                                    additional_ids.add(id_val)

    # Если нашли дополнительные id – добавляем их как новые продукты
    if additional_ids:
        # Находим позиции для каждого id в основном индексе
        new_positions = []
        for id_val in additional_ids:
            if id_val in index:
                for pos in index[id_val]:
                    new_positions.append((pos[0], pos[1], id_val))
        if new_positions:
            # Добавляем новые продукты в словарь products (если их ещё нет)
            for row_idx, col_idx, art in new_positions:
                row = data[row_idx]
                code = row.get("Код", "")
                view = row.get("Вид товара", "")
                fandom = row.get("Фандом", "") or row.get("Фандом 4ek", "")
                name = row.get("Название", "")
                key = (code, view, fandom, name)
                if key in products:
                    continue
                new_prod = {
                    "Код": code,
                    "Вид": view,
                    "Фандом": fandom,
                    "Название": name,
                    "Маркировки": set(),
                    "entries": [],
                    "skip_stickers": False,
                    "qr_markings": set(),
                    "sticker_art_pairs": [],
                }
                marking, is_id = get_marking_for_position(col_idx, col_names)
                if marking:
                    if marking == "FSK" and found_via_fsk:
                        new_prod["skip_stickers"] = True
                    else:
                        new_prod["Маркировки"].add(marking)
                        new_prod["entries"].append((marking, is_id))
                products[key] = new_prod

            # ---- ПЕРЕСЧИТЫВАЕМ sticker_markings ДЛЯ ВСЕХ ПРОДУКТОВ (включая новые) ----
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

            # ---- Строим таблицы для новых продуктов и добавляем в results ----
            for key, data_item in products.items():
                # Пропускаем уже обработанные (первые results)
                if any(res["Код"] == data_item["Код"] and res["Вид"] == data_item["Вид"] for res in results):
                    continue
                row_for_table = None
                # ищем строку по коду
                if data_item["Код"] in index:
                    pos = index[data_item["Код"]][0]
                    row_for_table = data[pos[0]]
                if row_for_table is None:
                    continue

                oz_pairs = data_item["sticker_art_pairs"] if found_via_qr and data_item["sticker_art_pairs"] else None
                table = get_row_data(
                    row_for_table,
                    col_names,
                    data_item["Код"],
                    sticker_indices,
                    oz_sticker_indices,
                    skip_stickers=data_item["skip_stickers"],
                    oz_search_art=None,
                    oz_sticker_art_pairs=oz_pairs
                )
                if table:
                    for row in table:
                        if row.get("platform") == "WB" and row.get("stickers"):
                            new_stickers = []
                            for st in row["stickers"]:
                                if isinstance(st, str):
                                    row_num = get_list_wb_row(
                                        row["marking"].split('_')[0] if '_' in row["marking"] else "",
                                        today_str,
                                        st
                                    )
                                    new_stickers.append({"sticker": st, "row": row_num if row_num is not None else None})
                                else:
                                    new_stickers.append(st)
                            row["stickers"] = new_stickers

                found_markings = list(data_item["sticker_markings"])
                if found_via_qr and data_item["qr_markings"]:
                    display_marking = ", ".join(sorted(f"{mk}_OZ" for mk in data_item["qr_markings"]))
                else:
                    display_marking = ", ".join(sorted(data_item["Маркировки"])) if data_item["Маркировки"] else None

                new_item = {
                    "Код": data_item["Код"],
                    "Вид": data_item["Вид"],
                    "Фандом": data_item["Фандом"],
                    "Название": data_item["Название"],
                    "Маркировка": display_marking,
                    "found_markings": found_markings,
                    "table": table
                }
                results.append(new_item)

    if not results:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    return results

@router.get("/mark")
async def mark_page():
    return FileResponse("static/mark.html")