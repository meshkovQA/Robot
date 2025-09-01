# app/services/robot_factory.py
# =======================================================================================
import logging
from typing import Dict, Any
from app.core.events.event_bus import EventBus
from app.infrastructure.hardware.controllers.hardware_controller import HardwareController
from app.infrastructure.hardware.controllers.sensor_controller import SensorManager
from app.services.robot.navigation_service import NavigationController
from app.services.robot.camera_service import CameraController
from app.services.robot.safety_service import SafetyController
from app.services.robot.robot_orchestrator import RobotOrchestrator

logger = logging.getLogger(__name__)


class RobotFactory:
    @staticmethod
    def create_robot(config: Dict[str, Any] = None) -> RobotOrchestrator:
        logger.info("🤖 Creating robot system...")
        config = config or {}

        try:
            # Создаем компоненты
            events = EventBus()

            hardware = HardwareController(
                events=events,
                bus=config.get('i2c_bus'),
            )

            sensors = SensorManager(
                hardware=hardware,
                events=events,
                update_interval=config.get('sensor_update_interval', 0.05)
            )

            safety = SafetyController(
                sensor_manager=sensors,
                events=events,
                config=config.get('safety_config', {})
            )

            camera = CameraController(
                hardware=hardware,
                events=events,
                config=config.get('camera_config', {})
            )

            navigation = NavigationController(
                hardware=hardware,
                safety=safety,
                camera=camera,
                events=events,
                config=config.get('navigation_config', {})
            )

            # Создаем оркестратор
            robot = RobotOrchestrator(
                hardware=hardware,
                sensors=sensors,
                navigation=navigation,
                camera=camera,
                safety=safety,
                events=events,
                config=config.get('robot_config', {})
            )

            # Инициализируем
            if robot.initialize():
                logger.info("✅ Robot created successfully")
                return robot
            else:
                raise RuntimeError("Failed to initialize robot")

        except Exception as e:
            logger.error(f"❌ Failed to create robot: {e}")
            raise
