# robot/ai_vision/home_ai_vision.py
"""
Home AI Vision - специализированное компьютерное зрение для домашнего робота.
Оптимизировано под домашние объекты и ситуации. Использует ТОЛЬКО
robot/ai_vision/home_mapping.py без локальных переопределений.
"""

from __future__ import annotations
from typing import List, Dict, Optional
import time
import logging
import numpy as np
import cv2

from robot.ai_vision.ai_vision import (
    AIVisionProcessor, DetectedObject, VisionState
)

# импортируем ТОЛЬКО из твоего маппинга
try:
    from robot.ai_vision.home_mapping import (
        get_home_object_name,
        is_important_for_home,
        map_to_russian,
        RUSSIAN_NAMES,           # можно не использовать, но пусть будет доступен
        guess_room_by_object_id  # пригодится для room_context (опционально)
    )
    MAPPING_AVAILABLE = True
except Exception as e:
    # если файла нет — работаем без домашней логики
    MAPPING_AVAILABLE = False

logger = logging.getLogger(__name__)


class HomeAIVision(AIVisionProcessor):
    """Домашнее AI-зрение, оптимизированное для квартиры/дома."""

    def __init__(self, camera=None):
        super().__init__(camera)

        # Настройки режима
        self.home_mode = MAPPING_AVAILABLE
        # EN подписи на оверлеях безопаснее (без ????)
        self.use_russian_names = False

        # Состояние/статистика
        self.home_object_history: Dict[str, List[Dict]] = {}
        self.room_context: str = "unknown"
        self.pet_detected = False
        self.owner_present = False

        logger.info("🏠 HomeAIVision initialized (mapping=%s)",
                    MAPPING_AVAILABLE)

    # ---- ЗАГРУЗКА ДЕТЕКТОРОВ (родитель делает основную инициализацию) ----
    def _init_detectors(self):
        super()._init_detectors()
        if not MAPPING_AVAILABLE:
            logger.warning(
                "Home mapping not available — using generic detectors only")
            self.home_mode = False

    # ---- ВСПОМОГАТЕЛЬНЫЕ: ИСПОЛЬЗУЕМ ТОЛЬКО home_mapping ----
    def _is_home_relevant(self, coco_class_id: int) -> bool:
        """Релевантность объекта для дома — только через home_mapping."""
        if not MAPPING_AVAILABLE:
            return False
        return is_important_for_home(coco_class_id)

    def _get_home_object_name(self, coco_class_id: int) -> Optional[str]:
        """Нормализованное EN-имя для объекта — только через home_mapping."""
        if not MAPPING_AVAILABLE:
            return None
        return get_home_object_name(coco_class_id, "")

    # Улучшенная детекция с мульти-моделью, NMS и «домашним» фильтром
    def _detect_with_yolo(self, frame) -> List[DetectedObject]:
        """
        Мульти-модельная детекция:
        – прогон нескольких YOLO-сетей, склейка детекций
        – NMS
        – фильтр "домашней" релевантности (если доступен mapping)
        – нормализация имён через home_mapping (если доступен)
        """
        if not getattr(self, "yolo_nets", None) or not self.yolo_nets:
            self._load_multimodel_detectors()

        if not self.yolo_nets:
            return []

        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame,
            scalefactor=1 / 255.0,
            size=self.yolo_input_size,
            swapRB=True,
            crop=False
        )

        boxes, confidences, class_ids = [], [], []

        for model_name, net in self.yolo_nets:
            try:
                net.setInput(blob)
                out_names = net.getUnconnectedOutLayersNames()
                layer_outputs = net.forward(out_names)
            except Exception as e:
                logger.warning(f"{model_name}: ошибка forward: {e}")
                continue

            for output in layer_outputs:
                for det in output:
                    scores = det[5:]
                    cid = int(np.argmax(scores))
                    cls_conf = float(scores[cid])
                    obj_conf = float(det[4]) if det.shape[0] >= 5 else 1.0
                    conf = cls_conf * obj_conf

                    if conf < self.yolo_conf_th:
                        continue

                    # если mapping есть — фильтруем по домашней релевантности
                    if MAPPING_AVAILABLE and not is_important_for_home(cid):
                        continue

                    bx = int(det[0] * w)
                    by = int(det[1] * h)
                    bw = int(det[2] * w)
                    bh = int(det[3] * h)
                    x = int(bx - bw / 2)
                    y = int(by - bh / 2)

                    boxes.append([x, y, bw, bh])
                    confidences.append(conf)
                    class_ids.append(cid)

        if not boxes:
            return []

        idxs = cv2.dnn.NMSBoxes(
            boxes, confidences, self.yolo_conf_th, self.yolo_nms_th)
        if isinstance(idxs, tuple) or isinstance(idxs, list):
            idxs = np.array(idxs).reshape(-1) if len(idxs) else np.array([])
        elif hasattr(idxs, "flatten"):
            idxs = idxs.flatten()
        else:
            idxs = np.array([])

        results: List[DetectedObject] = []
        now_ts = time.time()

        for i in idxs:
            cid = class_ids[i]

            # имя класса: из home_mapping, если доступен; иначе — из self.yolo_classes
            if MAPPING_AVAILABLE:
                name_en = get_home_object_name(cid, "") or (
                    self.yolo_classes[cid] if cid < len(
                        self.yolo_classes) else f"class_{cid}"
                )
            else:
                name_en = self.yolo_classes[cid] if cid < len(
                    self.yolo_classes) else f"class_{cid}"

            x, y, bw, bh = boxes[i]
            cx = x + bw // 2
            cy = y + bh // 2

            obj = DetectedObject(
                class_name=name_en,
                confidence=float(confidences[i]),
                bbox=(x, y, bw, bh),
                center=(cx, cy),
                area=float(bw * bh),
                timestamp=now_ts
            )
            results.append(obj)

            # обновим домашний контекст (безопасно: если mapping нет, часть шагов пропустится)
            self._update_home_context(name_en, cid, float(confidences[i]))

        return results

    def _load_multimodel_detectors(self):
        """
        Загружает несколько YOLO-моделей, если они есть на диске.
        Используем базовый self.yolo_net из super()._init_detectors(),
        плюс пытаемся добавить yolov3-tiny как вторую модель.
        """
        from pathlib import Path

        self.yolo_nets = []
        self.yolo_input_size = (416, 416)
        self.yolo_conf_th = 0.35   # чуть ниже базового порога — отфильтруем NMS
        self.yolo_nms_th = 0.45

        models_dir = Path("models/yolo")
        coco_path = models_dir / "coco.names"

        # классы COCO (если в базовом не подхватились)
        if not getattr(self, "yolo_classes", None):
            if coco_path.exists():
                with open(coco_path, "r", encoding="utf-8") as f:
                    self.yolo_classes = [ln.strip() for ln in f if ln.strip()]
            else:
                self.yolo_classes = []

        # 1) уже загруженный super()._init_yolo() — добавим как первую модель
        if getattr(self, "yolo_net", None) is not None:
            self.yolo_nets.append(("yolov4-tiny", self.yolo_net))

        # 2) попробовать yolov3-tiny (если есть)
        v3w = models_dir / "yolov3-tiny.weights"
        v3c = models_dir / "yolov3-tiny.cfg"
        try:
            if v3w.exists() and v3c.exists():
                net_v3 = cv2.dnn.readNet(str(v3w), str(v3c))
                self.yolo_nets.append(("yolov3-tiny", net_v3))
        except Exception as e:
            logger.warning(f"Не удалось загрузить yolov3-tiny: {e}")

        if not self.yolo_nets:
            logger.info(
                "YOLO-модели не найдены — детекция будет ограниченной (Haar и пр.).")
        else:
            logger.info("Загружены YOLO-модели: " +
                        ", ".join(name for name, _ in self.yolo_nets))

    # ---- КОНТЕКСТ ДОМА ----
    def _update_home_context(self, name_en: str, coco_class_id: int, confidence: float):
        """Обновляем признаки: питомцы, человек, комната и краткую историю."""
        # питомцы
        if name_en in ("cat", "dog"):
            self.pet_detected = True

        # присутствие человека
        if name_en == "person" and confidence > 0.7:
            self.owner_present = True

        # догадка по комнате (если импортировали утилиту)
        if MAPPING_AVAILABLE:
            room = guess_room_by_object_id(coco_class_id)
            if room:
                self.room_context = room

        # история
        self.home_object_history.setdefault(name_en, []).append({
            "timestamp": time.time(),
            "confidence": confidence
        })
        if len(self.home_object_history[name_en]) > 100:
            self.home_object_history[name_en] = self.home_object_history[name_en][-100:]

    # ---- ТЕКСТ ОПИСАНИЯ СЦЕНЫ ----
    def _generate_scene_description(self) -> str:
        parts: List[str] = []

        # люди по каскаду лиц (быстро и стабильно)
        faces_cnt = len(self.state.faces)
        if faces_cnt > 0:
            if self.use_russian_names:
                parts.append("человек" if faces_cnt ==
                             1 else f"{faces_cnt} человека")
            else:
                parts.append("person" if faces_cnt ==
                             1 else f"{faces_cnt} persons")

        # домашние животные
        pets = [
            o for o in self.state.objects if o.class_name in ("cat", "dog")]
        for p in pets:
            parts.append(map_to_russian(p.class_name)
                         if self.use_russian_names else p.class_name)

        # важные прочие объекты (чтобы не засорять список)
        important = [o for o in self.state.objects if o.class_name not in (
            "cat", "dog", "person") and o.confidence > 0.6]
        if important:
            counts: Dict[str, int] = {}
            for o in important:
                key = map_to_russian(
                    o.class_name) if self.use_russian_names else o.class_name
                counts[key] = counts.get(key, 0) + 1
            for name, cnt in counts.items():
                parts.append(name if cnt == 1 else f"{cnt} {name}")

        # префикс комнаты
        prefix = ""
        if self.room_context and self.room_context != "unknown":
            room_map_ru = {
                "kitchen": "кухня",
                "bedroom": "спальня",
                "living_room": "гостиная",
                "bathroom": "ванная",
                "office": "кабинет"
            }
            if self.use_russian_names:
                prefix = f"[{room_map_ru.get(self.room_context, self.room_context)}] "
            else:
                prefix = f"[{self.room_context}] "

        # движение
        if self.state.motion_detected:
            parts.append("движение" if self.use_russian_names else "movement")

        if not parts:
            return prefix + ("пустая комната" if self.use_russian_names else "empty room")

        return prefix + ("Вижу: " if self.use_russian_names else "I see: ") + ", ".join(parts)

    # ---- ПУБЛИЧНЫЕ УТИЛИТЫ ----
    def is_pet_present(self) -> bool:
        with self._lock:
            return any(o.class_name in ("cat", "dog") for o in self.state.objects)

    def get_pets_info(self) -> List[Dict]:
        with self._lock:
            info = []
            for o in self.state.objects:
                if o.class_name in ("cat", "dog"):
                    info.append({
                        "type": o.class_name,
                        "confidence": o.confidence,
                        "position": o.center,
                        "size": "large" if o.area > 5000 else "medium" if o.area > 1000 else "small"
                    })
            return info

    def is_person_sitting(self) -> bool:
        with self._lock:
            people = [o for o in self.state.objects if o.class_name == "person"]
            furn = [o for o in self.state.objects if o.class_name in (
                "chair", "sofa")]
            for p in people:
                for f in furn:
                    dx = p.center[0] - f.center[0]
                    dy = p.center[1] - f.center[1]
                    if (dx*dx + dy*dy) ** 0.5 < 100:
                        return True
            return False

    def get_room_context(self) -> str:
        return self.room_context

    def get_home_objects_stats(self) -> Dict:
        stats: Dict[str, Dict] = {}
        now = time.time()
        for name, hist in self.home_object_history.items():
            recent = [h for h in hist if now - h["timestamp"] < 300]
            if recent:
                avg = sum(h["confidence"] for h in recent) / len(recent)
                stats[name] = {
                    "detections_count": len(recent),
                    "avg_confidence": round(avg, 2),
                    "last_seen": max(h["timestamp"] for h in recent)
                }
        return stats

    def is_safe_for_movement(self) -> Dict[str, bool]:
        with self._lock:
            pets_clear = not any(o.class_name in ("cat", "dog")
                                 for o in self.state.objects)
            person_not_in_path = True
            furniture_clear = True

            # человек в центральной зоне
            for o in self.state.objects:
                if o.class_name == "person":
                    if 200 <= o.center[0] <= 440:
                        person_not_in_path = False
                        break

            # мебель по центру (простая эвристика)
            for o in self.state.objects:
                if o.class_name in ("chair", "table"):
                    if 200 <= o.center[0] <= 440:
                        furniture_clear = False
                        break

            overall = pets_clear and person_not_in_path and furniture_clear
            return {
                "pets_clear": pets_clear,
                "person_not_in_path": person_not_in_path,
                "furniture_clear": furniture_clear,
                "overall_safe": overall
            }

    def get_navigation_hints(self) -> List[str]:
        hints: List[str] = []

        if self.is_pet_present():
            for pet in self.get_pets_info():
                if pet["type"] == "cat":
                    hints.append(
                        "Осторожно: кот в зоне видимости — двигайтесь медленно")
                elif pet["type"] == "dog":
                    hints.append(
                        "Внимание: собака рядом — возможна реакция на движение")

        if self.room_context == "kitchen":
            hints.append("Кухня: осторожно с техникой и жидкостями на полу")
        elif self.room_context == "bedroom":
            hints.append("Спальня: двигайтесь тихо, возможно кто-то спит")
        elif self.room_context == "living_room":
            hints.append("Гостиная: много мебели — планируйте маршрут")

        if self.owner_present:
            hints.append("Рядом человек — дайте дорогу")

        return hints
