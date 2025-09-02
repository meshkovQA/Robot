# robot/ai_vision/ai_mapping.py
"""
Простой маппинг классов COCO для AI детекции
"""

# Базовые классы COCO (80 классов)
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"
]


def get_class_name(class_id: int) -> str:
    """Получить имя класса по ID"""
    if 0 <= class_id < len(COCO_CLASSES):
        return COCO_CLASSES[class_id]
    return f"unknown_{class_id}"


def get_display_color(class_name: str) -> tuple:
    """Простые цвета для отображения разных классов"""
    colors = {
        "person": (0, 255, 0),      # зеленый для людей
        "cat": (255, 0, 255),       # магента для кошек
        "dog": (255, 165, 0),       # оранжевый для собак
        "car": (0, 0, 255),         # синий для машин
        "bicycle": (255, 255, 0),   # желтый для велосипедов
    }
    return colors.get(class_name, (0, 255, 255))  # голубой по умолчанию
