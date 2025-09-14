# robot/components/__init__.py
"""
Компонентная архитектура робота

Этот модуль содержит все компоненты, разделенные по функциональности:
- MovementController - управление движением
- CameraController - управление камерой  
- KickstartManager - логика кикстарта моторов
- RGBController - управление RGB светодиодами
- SensorMonitor - мониторинг датчиков и автостоп
- ArmController - управление роботурукой
"""

from .movement_controller import MovementController
from .camera_controller import CameraController
from .kickstart_manager import KickstartManager
from .rgb_controller import RGBController
from .sensor_monitor import SensorMonitor
from .arm_controller import ArmController

__all__ = [
    'MovementController',
    'CameraController',
    'KickstartManager',
    'RGBController',
    'SensorMonitor',
    'ArmController'
]
