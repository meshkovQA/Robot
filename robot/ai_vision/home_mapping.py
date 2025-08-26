# robot/ai_vision/home_mapping.py
HOME_OBJECT_MAPPING = {
    0: "person",            1: "bicycle",        2: "car",            3: "motorcycle",
    4: "airplane",          5: "bus",            6: "train",          7: "truck",
    8: "boat",              9: "traffic light", 10: "fire hydrant",  11: "stop sign",
    12: "parking meter",   13: "bench",         14: "bird",          15: "cat",
    16: "dog",             17: "horse",         18: "sheep",         19: "cow",
    20: "elephant",        21: "bear",          22: "zebra",         23: "giraffe",
    24: "backpack",        25: "umbrella",      26: "handbag",       27: "tie",
    28: "suitcase",        29: "frisbee",       30: "skis",          31: "snowboard",
    32: "sports ball",     33: "kite",          34: "baseball bat",  35: "baseball glove",
    36: "skateboard",      37: "surfboard",     38: "tennis racket", 39: "bottle",
    40: "wine glass",      41: "cup",           42: "fork",          43: "knife",
    44: "spoon",           45: "bowl",          46: "banana",        47: "apple",
    48: "sandwich",        49: "orange",        50: "broccoli",      51: "carrot",
    52: "hot dog",         53: "pizza",         54: "donut",         55: "cake",
    56: "chair",           57: "sofa",          58: "plant",         59: "bed",
    60: "table",           61: "toilet",        62: "tv",            63: "laptop",
    64: "mouse",           65: "remote",        66: "keyboard",      67: "phone",
    68: "microwave",       69: "oven",          70: "toaster",       71: "sink",
    72: "fridge",          73: "book",          74: "clock",         75: "vase",
    76: "scissors",        77: "teddy bear",    78: "hair dryer",    79: "toothbrush",
}

# Упрощение/унификация имён (если разные модели дают разный вариант)
SIMPLIFIED_NAMES = {
    "cell phone": "phone",
    "tvmonitor": "tv",
    "pottedplant": "plant",
    "dining table": "table",
    "refrigerator": "fridge",
    "hair drier": "hair dryer",
    "wineglass": "wine glass",
}

# Русские названия (для твоего режима RU; можно не включать на оверлеях, чтобы не было "????")
RUSSIAN_NAMES = {
    "person": "человек", "bicycle": "велосипед", "car": "авто", "motorcycle": "мотоцикл",
    "airplane": "самолет", "bus": "автобус", "train": "поезд", "truck": "грузовик",
    "boat": "лодка", "traffic light": "светофор", "fire hydrant": "гидрант",
    "stop sign": "знак стоп", "parking meter": "паркомат", "bench": "скамейка",
    "bird": "птица", "cat": "кот", "dog": "собака", "horse": "лошадь",
    "sheep": "овца", "cow": "корова", "elephant": "слон", "bear": "медведь",
    "zebra": "зебра", "giraffe": "жираф", "backpack": "рюкзак", "umbrella": "зонт",
    "handbag": "сумка", "tie": "галстук", "suitcase": "чемодан", "frisbee": "фрисби",
    "skis": "лыжи", "snowboard": "сноуборд", "sports ball": "мяч", "kite": "кайт",
    "baseball bat": "бита", "baseball glove": "бейсб. перчатка", "skateboard": "скейт",
    "surfboard": "серф", "tennis racket": "ракетка", "bottle": "бутылка",
    "wine glass": "бокал", "cup": "чашка", "fork": "вилка", "knife": "нож",
    "spoon": "ложка", "bowl": "миска", "banana": "банан", "apple": "яблоко",
    "sandwich": "сэндвич", "orange": "апельсин", "broccoli": "брокколи",
    "carrot": "морковь", "hot dog": "хот-дог", "pizza": "пицца", "donut": "пончик",
    "cake": "торт", "chair": "стул", "sofa": "диван", "plant": "растение",
    "bed": "кровать", "table": "стол", "toilet": "туалет", "tv": "телевизор",
    "laptop": "ноутбук", "mouse": "мышь", "remote": "пульт", "keyboard": "клавиатура",
    "phone": "телефон", "microwave": "микроволновка", "oven": "духовка",
    "toaster": "тостер", "sink": "раковина", "fridge": "холодильник",
    "book": "книга", "clock": "часы", "vase": "ваза", "scissors": "ножницы",
    "teddy bear": "плюшевый мишка", "hair dryer": "фен", "toothbrush": "зубная щетка",
}

# Категории (удобно для логики безопасности/подсказок)
HOME_CATEGORIES = {
    "people_pets": {"person", "cat", "dog"},
    "furniture": {"chair", "sofa", "bed", "table"},
    "kitchenware": {"bottle", "wine glass", "cup", "bowl", "fork", "knife", "spoon"},
    "appliances": {"microwave", "oven", "toaster", "sink", "fridge", "tv"},
    "office": {"laptop", "keyboard", "mouse", "phone", "remote", "book", "clock"},
    "toilet_bath": {"toilet", "toothbrush", "hair dryer"},
    "decor": {"plant", "vase"},
    "toys": {"teddy bear"},
    "food": {"banana", "apple", "orange", "sandwich", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake"},
    "bags": {"backpack", "handbag", "suitcase"},
    "outer": {"umbrella", "tie"},
    # «outdoor/transport/sport» оставляем не-домашним по умолчанию
}

# Домашняя релевантность (по умолчанию: только действительно полезное в квартире)
HOME_RELEVANT_IDS = {
    0, 15, 16,                           # человек, кот, собака
    56, 57, 58, 59, 60,                  # мебель/растения
    61, 62, 63, 64, 65, 66, 67,          # санузел/электроника
    68, 69, 70, 71, 72,                  # кухня техника
    39, 40, 41, 42, 43, 44, 45,          # посуда
    46, 47, 48, 49, 50, 51, 52, 53, 54, 55,  # еда/упаковки
    73, 74, 75, 76, 77, 78, 79,          # офис/декор/мелочи
    24, 26, 28, 25, 27                   # сумки/зонт/галстук
}

# Релевантность по комнатам (для room_context, навигации, приоритетов)
ROOM_RELEVANCE = {
    "kitchen":  {68, 69, 70, 71, 72, 39, 41, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55},
    "living_room": {56, 57, 58, 60, 62, 65, 73, 74, 75, 77},
    "bedroom": {59, 73, 74, 77},
    "bathroom": {61, 71, 78, 79},
    "office": {63, 64, 66, 67, 73, 65, 62},
}

# Полезные утилиты (можно импортировать в твоём классе при отсутствии robot.home_mapping)


def get_home_object_name(coco_class_id: int, coco_name: str = "") -> str | None:
    """Вернёт нормализованное EN имя для домашнего отображения (или None, если нерелевантно)."""
    name = HOME_OBJECT_MAPPING.get(coco_class_id)
    if not name:
        return None
    name = SIMPLIFIED_NAMES.get(name, name)
    return name


def is_important_for_home(coco_class_id: int) -> bool:
    """Простой фильтр релевантности для квартиры/дома."""
    return coco_class_id in HOME_RELEVANT_IDS


def map_to_russian(name_en: str) -> str:
    """Безопасное преобразование EN → RU (если ключ есть)."""
    key = SIMPLIFIED_NAMES.get(name_en, name_en)
    return RUSSIAN_NAMES.get(key, key)


def guess_room_by_object_id(coco_class_id: int) -> str | None:
    """Попробовать вывести комнату по объекту (kitchen / living_room / bedroom / bathroom / office)."""
    for room, ids in ROOM_RELEVANCE.items():
        if coco_class_id in ids:
            return room
    return None
