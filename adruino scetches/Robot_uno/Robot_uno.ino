#include <Wire.h>
#include <Servo.h>
#include "DHT.h"

// ---------------- Пины моторов (DRV8871) ----------------
// Левый драйвер
#define LEFT_MOTOR_IN1 7        // НЕ PWM
#define LEFT_MOTOR_IN2 6        // PWM (Timer0)

// Правый драйвер
#define RIGHT_MOTOR_IN1 4       // НЕ PWM
#define RIGHT_MOTOR_IN2 5       // PWM (Timer0)

// Если вдруг «вперёд» у колеса обратный — инвертируй тут:
bool LEFT_DIR_INVERT  = true;
bool RIGHT_DIR_INVERT = true;

// ---------------- Сервомоторы камеры --------------------
#define CAMERA_PAN_PIN A0
#define CAMERA_TILT_PIN 10
Servo panServo;
Servo tiltServo;

// Плавность камеры
const int CAM_STEP = 2;          // град./шаг
const unsigned long CAM_STEP_MS = 15; // мс между шагами

// ---------------- Энкодеры -------------------------------
#define L_ENC_A 2   // внешнее прерывание INT0
#define L_ENC_B 8
#define R_ENC_A 3   // внешнее прерывание INT1
#define R_ENC_B 9

// Настройки расчёта скорости
const float CPR  = 1320.0;     // импульсов на оборот вала (A+B)
const float GEAR = 1.0;       // редуктор
const float WHEEL_D = 0.065;  // м

float lastLeftMps = 0, lastRightMps = 0;
unsigned long lastSpeedCalcMs = 0;

// ---------------- I2C -------------------------------
#define I2C_ADDRESS 8

// ---------------- DHT11 -----------------------------
#define DHTPIN 11
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);
float dhtTemperature = NAN;
float dhtHumidity    = NAN;
unsigned long dhtLastReadMs = 0;

// ---------------- Камера ----------------------------
int panAngle = 90;     // текущий угол
int tiltAngle = 90;
int panTarget = 90;    // целевой угол
int tiltTarget = 90;

const int PAN_MIN = 0, PAN_MAX = 180;
const int TILT_MIN = 50, TILT_MAX = 150;

unsigned long camLastStepMs = 0;

// ---------------- Команда от RPi --------------------
struct Command {
  int speed;        // -255..255
  int direction;    // 0=стоп, 1=вперёд, 2=назад, 3=танк_влево, 4=танк_вправо
  int panAngle;
  int tiltAngle;
};
Command currentCommand = {0, 0, 90, 90};

// «мертвая зона»
const int MIN_MOTOR_SPEED = 50;
const int DEAD_ZONE_COMPENSATION = 30;
int correctMotorSpeed(int sp) {
  if (sp == 0) return 0;
  int s = abs(sp);
  if (s > 0 && s < MIN_MOTOR_SPEED) s = MIN_MOTOR_SPEED + DEAD_ZONE_COMPENSATION;
  return (sp >= 0) ? s : -s;
}

// ---------------- Счётчики энкодеров ----------------
volatile long leftCount = 0, rightCount = 0;
volatile unsigned long lastLt = 0, lastRt = 0;
const unsigned long MIN_ISR_US = 100; // антидребезг

void isrLeftA(){
  unsigned long now = micros(); if (now - lastLt < MIN_ISR_US) return; lastLt = now;
  bool A = digitalRead(L_ENC_A), B = digitalRead(L_ENC_B);
  if (A ^ B) leftCount++; else leftCount--;
}
void isrRightA(){
  unsigned long now = micros(); if (now - lastRt < MIN_ISR_US) return; lastRt = now;
  bool A = digitalRead(R_ENC_A), B = digitalRead(R_ENC_B);
  if (A ^ B) rightCount++; else rightCount--;
}

// ---------------- Моторные утилиты ------------------
void setLeftRaw(int sp){ // -255..255
  sp = constrain(sp, -255, 255);
  if (LEFT_DIR_INVERT) sp = -sp;

  if (sp > 0) {
    digitalWrite(LEFT_MOTOR_IN1, LOW);
    analogWrite(LEFT_MOTOR_IN2, sp);
  } else if (sp < 0) {
    digitalWrite(LEFT_MOTOR_IN1, HIGH);
    analogWrite(LEFT_MOTOR_IN2, 255 - min(255, -sp));
  } else {
    analogWrite(LEFT_MOTOR_IN2, 0);
    digitalWrite(LEFT_MOTOR_IN1, LOW);
  }
}
void setRightRaw(int sp){ // -255..255
  sp = constrain(sp, -255, 255);
  if (RIGHT_DIR_INVERT) sp = -sp;

  if (sp > 0) {
    digitalWrite(RIGHT_MOTOR_IN1, LOW);
    analogWrite(RIGHT_MOTOR_IN2, sp);
  } else if (sp < 0) {
    digitalWrite(RIGHT_MOTOR_IN1, HIGH);
    analogWrite(RIGHT_MOTOR_IN2, 255 - min(255, -sp));
  } else {
    analogWrite(RIGHT_MOTOR_IN2, 0);
    digitalWrite(RIGHT_MOTOR_IN1, LOW);
  }
}
void stopAllMotors(){
  analogWrite(LEFT_MOTOR_IN2, 0);
  digitalWrite(LEFT_MOTOR_IN1, LOW);
  analogWrite(RIGHT_MOTOR_IN2, 0);
  digitalWrite(RIGHT_MOTOR_IN1, LOW);
}

// ---------------- I2C -------------------------------
void receiveCommand(int bytes) {
  byte buffer[8];
  int index = 0;
  while (Wire.available() && index < 8) buffer[index++] = Wire.read();
  while (Wire.available()) Wire.read();

  if (index >= 8) {
    currentCommand.speed     = buffer[0] | (buffer[1] << 8);
    currentCommand.direction = buffer[2] | (buffer[3] << 8);
    int newPan  = buffer[4] | (buffer[5] << 8);
    int newTilt = buffer[6] | (buffer[7] << 8);

    if (currentCommand.speed > 32767) currentCommand.speed -= 65536;

    if (newPan  >= PAN_MIN  && newPan  <= PAN_MAX)  panTarget  = newPan;
    if (newTilt >= TILT_MIN && newTilt <= TILT_MAX) tiltTarget = newTilt;
  }
}

void sendSensorData() {
  // pan, tilt, t10, h10, vL*100, vR*100  => 12 байт
  byte dataToSend[12];

  dataToSend[0] = panAngle & 0xFF;
  dataToSend[1] = (panAngle >> 8) & 0xFF;
  dataToSend[2] = tiltAngle & 0xFF;
  dataToSend[3] = (tiltAngle >> 8) & 0xFF;

  int16_t t10 = (isnan(dhtTemperature) ? -32768 : (int16_t)(dhtTemperature * 10));
  int16_t h10 = (isnan(dhtHumidity)    ? -32768 : (int16_t)(dhtHumidity    * 10));
  dataToSend[4] = t10 & 0xFF;  dataToSend[5] = (t10 >> 8) & 0xFF;
  dataToSend[6] = h10 & 0xFF;  dataToSend[7] = (h10 >> 8) & 0xFF;

  int16_t l100 = (int16_t)(lastLeftMps  * 100);
  int16_t r100 = (int16_t)(lastRightMps * 100);
  dataToSend[8]  = l100 & 0xFF;  dataToSend[9]  = (l100 >> 8) & 0xFF;
  dataToSend[10] = r100 & 0xFF;  dataToSend[11] = (r100 >> 8) & 0xFF;

  Wire.write(dataToSend, 12);
}

// --------- Плавное обновление камеры ----------
void updateCameraSmooth() {
  unsigned long now = millis();
  if (now - camLastStepMs < CAM_STEP_MS) return;
  camLastStepMs = now;

  if (panAngle != panTarget) {
    int dir = (panTarget > panAngle) ? 1 : -1;
    panAngle += dir * CAM_STEP;
    if ((dir > 0 && panAngle > panTarget) || (dir < 0 && panAngle < panTarget))
      panAngle = panTarget;
    panAngle = constrain(panAngle, PAN_MIN, PAN_MAX);
    panServo.write(panAngle);
  }
  if (tiltAngle != tiltTarget) {
    int dir = (tiltTarget > tiltAngle) ? 1 : -1;
    tiltAngle += dir * CAM_STEP;
    if ((dir > 0 && tiltAngle > tiltTarget) || (dir < 0 && tiltAngle < tiltTarget))
      tiltAngle = tiltTarget;
    tiltAngle = constrain(tiltAngle, TILT_MIN, TILT_MAX);
    tiltServo.write(tiltAngle);
  }
}

// ---------------- Камера ----------------------------
void setupCameraServos() {
  panServo.attach(CAMERA_PAN_PIN);
  tiltServo.attach(CAMERA_TILT_PIN);
  panServo.write(panAngle);
  tiltServo.write(tiltAngle);
  panTarget = panAngle;
  tiltTarget = tiltAngle;
  delay(300);
}

// ---------------- Мотор-команды ---------------------
void executeCommand() {
  int rawSpeed = constrain(currentCommand.speed, -255, 255);
  
  switch (currentCommand.direction) {
    case 0: // Стоп
      stopAllMotors(); 
      break;
      
    case 1: // Вперед
      {
        int correctedSpeed = correctMotorSpeed(rawSpeed);
        setLeftRaw(correctedSpeed); 
        setRightRaw(correctedSpeed); 
        break;
      }
      
    case 2: // Назад  
      {
        int correctedSpeed = correctMotorSpeed(rawSpeed);
        setLeftRaw(-correctedSpeed); 
        setRightRaw(-correctedSpeed); 
        break;
      }
      
    case 3: // Поворот влево (танк)
      {
        int turnSpeed = (rawSpeed == 0) ? 150 : rawSpeed;
        int correctedSpeed = correctMotorSpeed(turnSpeed);
        setLeftRaw(-correctedSpeed); 
        setRightRaw(correctedSpeed); 
        break;
      }
      
    case 4: // Поворот вправо (танк)
      {
        int turnSpeed = (rawSpeed == 0) ? 150 : rawSpeed;
        int correctedSpeed = correctMotorSpeed(turnSpeed);
        setLeftRaw(correctedSpeed); 
        setRightRaw(-correctedSpeed); 
        break;
      }
      
    default: 
      stopAllMotors(); 
      break;
  }
}

// ---------------- Setup / Loop ----------------------
void setup() {
  Serial.begin(115200);

  Wire.begin(I2C_ADDRESS);
  Wire.onReceive(receiveCommand);
  Wire.onRequest(sendSensorData);

  pinMode(LEFT_MOTOR_IN1, OUTPUT);
  pinMode(LEFT_MOTOR_IN2, OUTPUT);
  pinMode(RIGHT_MOTOR_IN1, OUTPUT);
  pinMode(RIGHT_MOTOR_IN2, OUTPUT);
  stopAllMotors();

  setupCameraServos();

  dht.begin();

  pinMode(L_ENC_A, INPUT_PULLUP);
  pinMode(L_ENC_B, INPUT_PULLUP);
  pinMode(R_ENC_A, INPUT_PULLUP);
  pinMode(R_ENC_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(L_ENC_A), isrLeftA, RISING);
  attachInterrupt(digitalPinToInterrupt(R_ENC_A), isrRightA, RISING);

  Serial.println("Controller ready");
}

void loop() {
  unsigned long now = millis();

  // DHT раз в 2 с
  if (now - dhtLastReadMs >= 2000) {
    dhtLastReadMs = now;
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (!isnan(h) && !isnan(t)) {
      dhtHumidity = h; dhtTemperature = t;
    }
  }

  // Плавная камера
  updateCameraSmooth();

  // Движение
  executeCommand();

  // Расчёт скоростей (кеш для I2C)
  static unsigned long t0 = 0;
  static long pL = 0, pR = 0;
  if (now - t0 >= 200) {
    noInterrupts(); long L = leftCount, R = rightCount; interrupts();
    long dL = L - pL, dR = R - pR; pL = L; pR = R;
    float dt = (now - t0) / 1000.0f; t0 = now;

    float l_cps = dL / dt;
    float r_cps = -(dR / dt);  // инверсия, чтобы «вперёд» было +
    float l_rpm = (l_cps / CPR) * 60.0f / GEAR;
    float r_rpm = (r_cps / CPR) * 60.0f / GEAR;

    float C = 3.1415926f * WHEEL_D;
    lastLeftMps  = (l_rpm / 60.0f) * C;
    lastRightMps = (r_rpm / 60.0f) * C;
  }

  delay(20); // ~50 Гц
}

// ---------------- Вспомогательные для камеры ----------
void setCameraPan(int angle) {
  angle = constrain(angle, PAN_MIN, PAN_MAX);
  panTarget = angle;
}
void setCameraTilt(int angle) {
  angle = constrain(angle, TILT_MIN, TILT_MAX);
  tiltTarget = angle;
}
void setCameraCenter() {
  panTarget = 90;
  tiltTarget = 90;
}