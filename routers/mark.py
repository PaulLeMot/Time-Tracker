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

def get_oz_data_for_qr(marking: str, date_str: str):
    """Возвращает словарь: QR-код (нижний штрихкод) -> список (стикер, верхний_штрихкод)"""
    cache_key = (marking, date_str, "oz_qr_data")
    if cache_key in _sticker_caches:
        return _sticker_caches[cache_key].get("qr_data", {})

    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "input", f"{marking}_OZ.csv")
    qr_data = {}

    if os.path.exists(file_path):
        try:
            df = None
            for sep in [';', ',']:
                try:
                    # Колонки: B (стикер = номер отправления), AD (верхний штрихкод), AE (нижний штрихкод)
                    df = pd.read_csv(file_path, header=None, usecols=[1, 29, 30], dtype=str, sep=sep, encoding='utf-8').fillna('')
                    break
                except Exception:
                    continue
            if df is None:
                df = pd.read_csv(file_path, header=None, usecols=[1, 29, 30], dtype=str, sep=None, engine='python', encoding='utf-8').fillna('')
            for _, row in df.iterrows():
                sticker = str(row.iloc[0]).strip()
                upper_barcode = str(row.iloc[1]).strip()
                qr = str(row.iloc[2]).strip()
                if sticker == 'Номер отправления' or qr == 'Нижний штрихкод':
                    continue
                if sticker and sticker != 'nan' and qr and qr != 'nan':
                    if qr not in qr_data:
                        qr_data[qr] = []
                    qr_data[qr].append({
                        "sticker": sticker,
                        "upper_barcode": upper_barcode if upper_barcode != 'nan' else None,
                        "marking": marking
                    })
            print(f"[OZ-QR] Загружен {marking}, записей: {len(qr_data)}")
        except Exception as e:
            print(f"Ошибка загрузки OZ-данных для {marking}: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[OZ-QR] Файл не найден: {file_path}")

    if cache_key not in _sticker_caches:
        _sticker_caches[cache_key] = {}
    _sticker_caches[cache_key]["qr_data"] = qr_data
    return qr_data

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

def get_row_data(row, col_names, code, sticker_indices, oz_sticker_indices, skip_stickers=False, oz_search_art=None, oz_sticker_upper_map=None):
    """
    oz_sticker_upper_map: dict {стикер: верхний_штрихкод} для фильтрации OZ-стикеров (только для QR-поиска)
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
        if not skip_stickers:
            if oz_sticker_upper_map is not None:
                # Используем только те стикеры, которые есть в oz_sticker_upper_map
                for sticker, upper_barcode in oz_sticker_upper_map.items():
                    oz_pairs.append({"sticker": sticker, "upper_barcode": upper_barcode})
            else:
                # Старая логика: ищем по артикулу
                search_art = oz_search_art if oz_search_art is not None else code
                stickers_for_art = oz_sticker_indices.get(mk, {}).get(search_art, [])
                for st in stickers_for_art:
                    oz_pairs.append({"sticker": st, "upper_barcode": None})
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

    found_via_fsk = False
    if barcode.startswith("2400000") and len(barcode) == 13:
        found_via_fsk = True

    # ===== СЛУЧАЙ 1: Поиск по артикулу (если введён артикул или FSK) =====
    if normalized in index:
        all_positions = []
        for pos in index[normalized]:
            all_positions.append((pos[0], pos[1], normalized))
        all_positions = list(set(all_positions))
        if not all_positions:
            raise HTTPException(status_code=404, detail="Товар не найден")
        
        products = {}
        for row_idx, col_idx, art in all_positions:
            row = data[row_idx]
            if art not in products:
                products[art] = {
                    "Код": row.get("Код", "").strip(),
                    "Вид": row.get("Вид товара", "").strip(),
                    "Фандом": (row.get("Фандом", "") or row.get("Фандом 4ek", "")).strip(),
                    "Название": row.get("Название", "").strip(),
                    "Маркировки": set(),
                    "entries": [],
                    "skip_stickers": False,
                    "row": row,
                }
            else:
                prod = products[art]
                if not prod["Вид"] and row.get("Вид товара"):
                    prod["Вид"] = row.get("Вид товара", "").strip()
                if not prod["Фандом"] and (row.get("Фандом") or row.get("Фандом 4ek")):
                    prod["Фандом"] = (row.get("Фандом") or row.get("Фандом 4ek", "")).strip()
                if not prod["Название"] and row.get("Название"):
                    prod["Название"] = row.get("Название", "").strip()
                if "row" not in prod:
                    prod["row"] = row

            marking, is_id = get_marking_for_position(col_idx, col_names)
            if marking:
                if marking == "FSK" and found_via_fsk:
                    products[art]["skip_stickers"] = True
                else:
                    products[art]["Маркировки"].add(marking)
                    products[art]["entries"].append((marking, is_id))

        for art, data_item in products.items():
            if data_item["skip_stickers"]:
                data_item["sticker_markings"] = set()
                continue
            id_markings = {marking for marking, is_id in data_item["entries"] if is_id is True}
            barcode_markings = {marking for marking, is_id in data_item["entries"] if is_id is False}
            data_item["sticker_markings"] = id_markings | barcode_markings

        results = []
        for art, data_item in products.items():
            row_for_table = data_item.get("row")
            if row_for_table is not None:
                table = get_row_data(
                    row_for_table,
                    col_names,
                    data_item["Код"],
                    sticker_indices,
                    oz_sticker_indices,
                    skip_stickers=data_item["skip_stickers"],
                    oz_search_art=art,
                    oz_sticker_upper_map=None
                )
            else:
                table = []

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
            display_marking = ", ".join(sorted(data_item["Маркировки"])) if data_item["Маркировки"] else None

            results.append({
                "Код": data_item["Код"],
                "Вид": data_item["Вид"],
                "Фандом": data_item["Фандом"],
                "Название": data_item["Название"],
                "Маркировка": display_marking,
                "found_markings": found_markings,
                "table": table
            })

        if not results:
            raise HTTPException(status_code=404, detail="Товар не найден")
        return results

    # ===== СЛУЧАЙ 2: Поиск по QR-коду (нижний штрихкод) =====
    # Собираем все QR->стикер из всех маркетплейсов
    qr_data_all = {}
    for mk in MARKING_KEYS:
        qr_data = get_oz_data_for_qr(mk, today_str)
        for qr, items in qr_data.items():
            if qr not in qr_data_all:
                qr_data_all[qr] = []
            qr_data_all[qr].extend(items)

    if barcode not in qr_data_all:
        raise HTTPException(status_code=404, detail="QR-код не найден в файлах OZ")

    qr_items = qr_data_all[barcode]  # список {sticker, upper_barcode, marking}

    # Группируем по маркетплейсу и стикеру, чтобы получить уникальные стикеры с их верхними штрихкодами
    sticker_upper_map = {}
    sticker_to_marking = {}
    for item in qr_items:
        sticker = item["sticker"]
        upper = item["upper_barcode"]
        marking = item["marking"]
        if sticker not in sticker_upper_map:
            sticker_upper_map[sticker] = upper
            sticker_to_marking[sticker] = marking
        # Если стикер уже есть, но верхний штрихкод отсутствовал, а сейчас есть — обновляем
        elif sticker_upper_map[sticker] is None and upper is not None:
            sticker_upper_map[sticker] = upper

    # Теперь по стикерам (номерам отправлений) нужно найти артикулы в основной таблице.
    # Но в основной таблице нет номера отправления. Вместо этого мы должны найти товары,
    # которые входят в этот заказ. Для этого нужно понять, как связаны стикер и артикул.
    # В Ozon-файле стикер (номер отправления) соответствует заказу, в котором есть несколько товаров.
    # Артикулы товаров есть в том же Ozon-файле (колонка P).
    # Поэтому мы можем пройти по всем строкам Ozon-файла с этим стикером и собрать артикулы.
    # Для этого нужно перечитать Ozon-файл и собрать соответствие стикер -> артикулы.
    
    # Получаем артикулы для каждого стикера из Ozon-файлов
    # Для этого используем существующую функцию get_oz_sticker_index, но она построена на артикул -> стикеры.
    # Построим обратный индекс: стикер -> артикулы.
    sticker_to_arts = {}
    for mk in MARKING_KEYS:
        # Загружаем соответствие артикул -> стикеры для этого маркетплейса
        oz_idx = get_oz_sticker_index(mk, today_str)
        for art, stickers in oz_idx.items():
            for st in stickers:
                if st not in sticker_to_arts:
                    sticker_to_arts[st] = []
                if art not in sticker_to_arts[st]:
                    sticker_to_arts[st].append(art)

    # Собираем все артикулы для найденных стикеров
    arts_to_search = []
    for sticker in sticker_upper_map.keys():
        if sticker in sticker_to_arts:
            arts_to_search.extend(sticker_to_arts[sticker])

    # Удаляем дубликаты артикулов
    arts_to_search = list(set(arts_to_search))

    if not arts_to_search:
        raise HTTPException(status_code=404, detail="По стикеру не найдено артикулов")

    # Ищем позиции по найденным артикулам в основной таблице
    all_positions = []
    for art in arts_to_search:
        if art in index:
            for pos in index[art]:
                all_positions.append((pos[0], pos[1], art))
    all_positions = list(set(all_positions))
    if not all_positions:
        raise HTTPException(status_code=404, detail="Товары не найдены по артикулам")

    # Группируем по коду товара
    products = {}
    for row_idx, col_idx, art in all_positions:
        row = data[row_idx]
        code = row.get("Код", "").strip()
        if not code:
            continue

        if code not in products:
            products[code] = {
                "Код": code,
                "Вид": row.get("Вид товара", "").strip(),
                "Фандом": (row.get("Фандом", "") or row.get("Фандом 4ek", "")).strip(),
                "Название": row.get("Название", "").strip(),
                "Маркировки": set(),
                "entries": [],
                "skip_stickers": False,
                "row": row,
                "sticker_upper_map": sticker_upper_map,  # сохраняем карту стикер->верхний штрихкод
            }
        else:
            prod = products[code]
            if not prod["Вид"] and row.get("Вид товара"):
                prod["Вид"] = row.get("Вид товара", "").strip()
            if not prod["Фандом"] and (row.get("Фандом") or row.get("Фандом 4ek")):
                prod["Фандом"] = (row.get("Фандом") or row.get("Фандом 4ek", "")).strip()
            if not prod["Название"] and row.get("Название"):
                prod["Название"] = row.get("Название", "").strip()
            if "row" not in prod:
                prod["row"] = row

        marking, is_id = get_marking_for_position(col_idx, col_names)
        if marking:
            if marking == "FSK" and found_via_fsk:
                products[code]["skip_stickers"] = True
            else:
                products[code]["Маркировки"].add(marking)
                products[code]["entries"].append((marking, is_id))

    # Вычисляем sticker_markings
    for code, data_item in products.items():
        if data_item["skip_stickers"]:
            data_item["sticker_markings"] = set()
            continue
        id_markings = {marking for marking, is_id in data_item["entries"] if is_id is True}
        barcode_markings = {marking for marking, is_id in data_item["entries"] if is_id is False}
        data_item["sticker_markings"] = id_markings | barcode_markings

    results = []
    for code, data_item in products.items():
        row_for_table = data_item.get("row")
        if row_for_table is not None:
            table = get_row_data(
                row_for_table,
                col_names,
                data_item["Код"],
                sticker_indices,
                oz_sticker_indices,
                skip_stickers=data_item["skip_stickers"],
                oz_search_art=None,
                oz_sticker_upper_map=data_item["sticker_upper_map"]  # передаём карту стикер->верхний штрихкод
            )
        else:
            table = []

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
        display_marking = ", ".join(sorted(data_item["Маркировки"])) if data_item["Маркировки"] else None

        results.append({
            "Код": data_item["Код"],
            "Вид": data_item["Вид"],
            "Фандом": data_item["Фандом"],
            "Название": data_item["Название"],
            "Маркировка": display_marking,
            "found_markings": found_markings,
            "table": table
        })

    if not results:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return results

@router.get("/mark")
async def mark_page():
    return FileResponse("static/mark.html")