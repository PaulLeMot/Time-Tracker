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
        # Проверяем также наличие файлов в папке list (только WB)
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
                    qr_index.setdefault(qr, []).append({"art": art, "marking": marking})
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

def get_list_wb_row(marking: str, date_str: str, sticker: str) -> int | None:
    """
    Ищет стикер в Excel-файле из папки list (только WB).
    Заголовки находятся в 5-й строке (индекс 4).
    Ищет колонку с заголовком "Стикер" (с большой буквы).
    Если не находит, пробует индексы 6 (G) и 5 (F) последовательно.
    """
    base_path = "/work/!МП_(FSk)/!FBS"
    file_path = os.path.join(base_path, f"{date_str}_FBS", "list", f"{marking}_WB.xlsx")
    if not os.path.exists(file_path):
        print(f"[LIST] Файл не найден: {file_path}")
        return None

    try:
        # Читаем строку 5 (индекс 4) как заголовки
        header_df = pd.read_excel(file_path, header=None, skiprows=4, nrows=1, dtype=str).fillna('')
        sticker_col_idx = None

        # Ищем колонку с заголовком "Стикер"
        for idx, val in enumerate(header_df.iloc[0]):
            if str(val).strip() == 'Стикер':
                sticker_col_idx = idx
                print(f"[LIST] Найдена колонка с заголовком 'Стикер' на индексе {idx}")
                break

        # Если не нашли, пробуем индексы 6 (G) и 5 (F)
        if sticker_col_idx is None:
            for idx in [6, 5]:
                try:
                    if idx < len(header_df.iloc[0]):
                        sticker_col_idx = idx
                        print(f"[LIST] Используем колонку с индексом {idx}")
                        break
                except:
                    pass

        if sticker_col_idx is None:
            print(f"[LIST] В файле {file_path} не найдена колонка с заголовком 'Стикер' и индексы 6,5 отсутствуют")
            return None

        # Читаем всю таблицу, берём только найденную колонку, пропускаем 5 строк (заголовки)
        df = pd.read_excel(file_path, header=None, usecols=[sticker_col_idx], dtype=str).fillna('')
        # Пропускаем первые 5 строк (заголовки)
        df = df.iloc[5:].reset_index(drop=True)

        clean_sticker = sticker.replace(' ', '')
        for idx, value in enumerate(df.iloc[:, 0]):
            clean_value = str(value).replace(' ', '')
            if clean_value == clean_sticker:
                row_num = idx + 1  # первая строка данных после заголовков
                print(f"[LIST] Найден стикер {sticker} в строке {row_num} (Excel строка {row_num + 5})")
                return row_num
    except Exception as e:
        print(f"[LIST] Ошибка поиска стикера в {file_path}: {e}")
        return None
    print(f"[LIST] Стикер {sticker} не найден в {file_path}")
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

    found_via_qr = False
    found_via_fsk = False
    qr_art_markings = {}  # art -> set(markings) – будет использоваться для маркировок, если нужно

    # Определяем, был ли введён FSK-штрихкод (начинается с 2400000 и длина 13)
    if barcode.startswith("2400000") and len(barcode) == 13:
        found_via_fsk = True

    if normalized in index:
        # Если это FSK или обычный артикул, ищем по нему
        barcodes_to_search = [normalized]
        # Для этого случая мы не будем использовать QR-логику, но чтобы сохранить единообразие,
        # мы можем просто искать по normalized
        all_positions = []
        for bcode in barcodes_to_search:
            if bcode in index:
                for pos in index[bcode]:
                    all_positions.append((pos[0], pos[1], bcode))
        all_positions = list(set(all_positions))
        if not all_positions:
            raise HTTPException(status_code=404, detail="Товар не найден")
        
        # Группируем по артикулу (bcode)
        products = {}
        for row_idx, col_idx, art in all_positions:
            row = data[row_idx]
            # Используем артикул как ключ
            if art not in products:
                products[art] = {
                    "Код": row.get("Код", "").strip(),
                    "Вид": row.get("Вид товара", "").strip(),
                    "Фандом": (row.get("Фандом", "") or row.get("Фандом 4ek", "")).strip(),
                    "Название": row.get("Название", "").strip(),
                    "Маркировки": set(),
                    "entries": [],
                    "skip_stickers": False,
                    "qr_markings": set(),
                    "row": row,
                }
            else:
                # Если артикул уже есть, обновляем поля, если они пустые
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
                    if marking == "FSK" and not found_via_qr and not found_via_fsk:
                        pass

        # Вычисляем sticker_markings
        for art, data_item in products.items():
            if data_item["skip_stickers"]:
                data_item["sticker_markings"] = set()
                continue

            qr_markings = {f"{mk}_OZ" for mk in data_item["qr_markings"]}
            id_markings = {marking for marking, is_id in data_item["entries"] if is_id is True}
            barcode_markings = {marking for marking, is_id in data_item["entries"] if is_id is False}
            all_markings = id_markings | barcode_markings | qr_markings
            data_item["sticker_markings"] = all_markings

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
                    oz_search_art=art  # передаём артикул для поиска стикеров OZ
                )
            else:
                table = []

            # Обогащение WB-стикеров
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

        if not results:
            raise HTTPException(status_code=404, detail="Товар не найден")
        return results

    else:
        # Поиск по QR-коду для OZ
        qr_index_all = {}
        for mk in MARKING_KEYS:
            qr_idx = get_oz_qr_index(mk, today_str)
            for qr, items in qr_idx.items():
                qr_index_all.setdefault(qr, []).extend(items)

        if barcode not in qr_index_all:
            raise HTTPException(status_code=404, detail="Товар не найден")

        found_via_qr = True
        qr_items = qr_index_all[barcode]

        # Дедуплицируем артикулы, чтобы избежать повторов
        art_set = set()
        for item in qr_items:
            art_set.add(item["art"])
        barcodes_to_search = list(art_set)

        all_positions = []
        for bcode in barcodes_to_search:
            if bcode in index:
                for pos in index[bcode]:
                    all_positions.append((pos[0], pos[1], bcode))
        all_positions = list(set(all_positions))
        if not all_positions:
            raise HTTPException(status_code=404, detail="Товар не найден")

        # Группируем по артикулу (bcode)
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
                    "qr_markings": set(),
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

            # Добавляем маркировки из QR, если артикул совпадает
            # Собираем маркировки для данного артикула
            for item in qr_items:
                if item["art"] == art:
                    products[art]["qr_markings"].add(item["marking"])

            marking, is_id = get_marking_for_position(col_idx, col_names)
            if marking:
                if marking == "FSK" and found_via_fsk:
                    products[art]["skip_stickers"] = True
                else:
                    products[art]["Маркировки"].add(marking)
                    products[art]["entries"].append((marking, is_id))
                    if marking == "FSK" and not found_via_qr and not found_via_fsk:
                        pass

        # Вычисляем sticker_markings
        for art, data_item in products.items():
            if data_item["skip_stickers"]:
                data_item["sticker_markings"] = set()
                continue

            qr_markings = {f"{mk}_OZ" for mk in data_item["qr_markings"]}
            id_markings = {marking for marking, is_id in data_item["entries"] if is_id is True}
            barcode_markings = {marking for marking, is_id in data_item["entries"] if is_id is False}
            all_markings = id_markings | barcode_markings | qr_markings
            data_item["sticker_markings"] = all_markings

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
                    oz_search_art=art
                )
            else:
                table = []

            # Обогащение WB-стикеров
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
            # Отображаем маркировку: если есть QR-маркировки, показываем их, иначе все маркировки
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

        if not results:
            raise HTTPException(status_code=404, detail="Товар не найден")
        return results

@router.get("/mark")
async def mark_page():
    return FileResponse("static/mark.html")