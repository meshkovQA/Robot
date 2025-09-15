#include <Wire.h>
#include <Servo.h>

// ---------- HC-SR04 ----------
#define LEFT_FRONT_TRIG   A5
#define LEFT_FRONT_ECHO   A4
#define RIGHT_FRONT_TRIG  A3
#define RIGHT_FRONT_ECHO  A2
#define LEFT_REAR_TRIG    A7
#define LEFT_REAR_ECHO    A6
#define FRONT_CENTER_TRIG A9
#define FRONT_CENTER_ECHO A8
#define REAR_RIGHT_TRIG   A11
#define REAR_RIGHT_ECHO   A10

// ---------- I2C ----------
#define I2C_ADDRESS 9
#define REG_RGB     0x10
#define REG_SERVO   0x31   // сразу вся рука

// ---------- RGB ----------
#define RGB_RED_PIN   12
#define RGB_GREEN_PIN 11
#define RGB_BLUE_PIN  10
int current_red=0,current_green=0,current_blue=0;

// ---------- Роборука ----------
Servo armServos[5];
const int armPins[5] = {4, 5, 6, 7, 8};
bool servoAttached[5] = {false, false, false, false, false};

// ограничения углов
const int SERVO_MIN[5] = {  0, 10, 50,  0, 65};
const int SERVO_MAX[5] = {180,140,180,180,120};

// текущие и целевые углы
int currentAngle[5] = {90,90,90,90,90};
int targetAngle[5]  = {90,90,90,90,90};

const int SERVO_STEP = 1;          // шаг в градусах
const int SERVO_DELAY_MS = 20;     // задержка между шагами

// ---------- Датчики ----------
int cached_left_front_distance=0;
int cached_right_front_distance=0;
int cached_left_rear_distance=0;
int cached_front_center_distance=0;
int cached_rear_right_distance=0;

// ---------- Функции ----------
void setupUltrasonicPins();
int getDistance(int trigPin, int echoPin);
void setupRGBLED();
void setRGBColor(int red, int green, int blue);
void receiveI2CCommand(int bytes);
void sendSensorData();

void attachServoIfNeeded(int id){
  if(id<0||id>4) return;
  if(!servoAttached[id]){
    armServos[id].attach(armPins[id]);
    servoAttached[id]=true;
  }
}
int clampAngle(int id,int angle){
  if(id<0||id>4) return angle;
  if(angle<SERVO_MIN[id]) angle=SERVO_MIN[id];
  if(angle>SERVO_MAX[id]) angle=SERVO_MAX[id];
  return angle;
}
void updateServosSmooth(){
  bool anyMoving=false;
  for(int i=0;i<5;i++){
    if(currentAngle[i]!=targetAngle[i]){
      anyMoving=true;
      int dir=(targetAngle[i]>currentAngle[i])?1:-1;
      currentAngle[i]+=dir*SERVO_STEP;
      if((dir>0 && currentAngle[i]>targetAngle[i]) ||
         (dir<0 && currentAngle[i]<targetAngle[i])){
        currentAngle[i]=targetAngle[i];
      }
      attachServoIfNeeded(i);
      armServos[i].write(currentAngle[i]);
    }
  }
  if(anyMoving) delay(SERVO_DELAY_MS);
}

void setup(){
  Serial.begin(9600);

  Wire.begin(I2C_ADDRESS);
  Wire.onRequest(sendSensorData);
  Wire.onReceive(receiveI2CCommand);

  setupUltrasonicPins();
  setupRGBLED();

  Serial.println(F("=== MEGA: датчики + RGB + роборука (пакетно) ==="));
  Serial.println(F("I2C RGB: [0x10,R,G,B]"));
  Serial.println(F("I2C ARM: [0x31,s0..s4] (5 байт углов)"));
}

void loop(){
  // датчики
  cached_left_front_distance   = getDistance(LEFT_FRONT_TRIG,LEFT_FRONT_ECHO);
  cached_right_front_distance  = getDistance(RIGHT_FRONT_TRIG,RIGHT_FRONT_ECHO);
  cached_left_rear_distance    = getDistance(LEFT_REAR_TRIG,LEFT_REAR_ECHO);
  cached_front_center_distance = getDistance(FRONT_CENTER_TRIG,FRONT_CENTER_ECHO);
  cached_rear_right_distance   = getDistance(REAR_RIGHT_TRIG,REAR_RIGHT_ECHO);

  // обновляем сервы плавно
  updateServosSmooth();

  delay(50);
}

// ---------- Датчики ----------
void setupUltrasonicPins(){
  pinMode(LEFT_FRONT_TRIG,OUTPUT); pinMode(LEFT_FRONT_ECHO,INPUT);
  pinMode(RIGHT_FRONT_TRIG,OUTPUT);pinMode(RIGHT_FRONT_ECHO,INPUT);
  pinMode(LEFT_REAR_TRIG,OUTPUT);  pinMode(LEFT_REAR_ECHO,INPUT);
  pinMode(FRONT_CENTER_TRIG,OUTPUT); pinMode(FRONT_CENTER_ECHO,INPUT);
  pinMode(REAR_RIGHT_TRIG,OUTPUT);   pinMode(REAR_RIGHT_ECHO,INPUT);
}
int getDistance(int trigPin,int echoPin){
  digitalWrite(trigPin,LOW); delayMicroseconds(2);
  digitalWrite(trigPin,HIGH);delayMicroseconds(10);
  digitalWrite(trigPin,LOW);
  long duration=pulseIn(echoPin,HIGH,30000UL);
  if(duration==0) return 999;
  int d=duration*0.034/2;
  if(d<2) return 2;
  if(d>400) return 999;
  return d;
}

// ---------- I2C ----------
void sendSensorData(){
  byte data[10];
  int v0=cached_left_front_distance;
  int v1=cached_right_front_distance;
  int v2=cached_left_rear_distance;
  int v3=cached_front_center_distance;
  int v4=cached_rear_right_distance;
  data[0]=v0&0xFF; data[1]=(v0>>8)&0xFF;
  data[2]=v1&0xFF; data[3]=(v1>>8)&0xFF;
  data[4]=v2&0xFF; data[5]=(v2>>8)&0xFF;
  data[6]=v3&0xFF; data[7]=(v3>>8)&0xFF;
  data[8]=v4&0xFF; data[9]=(v4>>8)&0xFF;
  Wire.write(data,10);
}

void receiveI2CCommand(int bytes){
  byte buf[16]; int n=0;
  while(Wire.available()&&n<sizeof(buf)) buf[n++]=Wire.read();
  if(n==0) return;
  byte reg=buf[0];
  if(reg==REG_RGB && n>=4){
    current_red=constrain(buf[1],0,255);
    current_green=constrain(buf[2],0,255);
    current_blue=constrain(buf[3],0,255);
    setRGBColor(current_red,current_green,current_blue);
  }
  else if(reg==REG_SERVO && n>=6){
    for(int i=0;i<5;i++){
      int angle=buf[1+i];
      targetAngle[i]=clampAngle(i,angle);
    }
    Serial.print(F("[I2C] Servo targets: "));
    for(int i=0;i<5;i++){Serial.print(targetAngle[i]); Serial.print(' ');}
    Serial.println();
  }
}

// ---------- RGB ----------
void setupRGBLED(){
  pinMode(RGB_RED_PIN,OUTPUT);
  pinMode(RGB_GREEN_PIN,OUTPUT);
  pinMode(RGB_BLUE_PIN,OUTPUT);
  setRGBColor(0,0,0);
}
void setRGBColor(int r,int g,int b){
  analogWrite(RGB_RED_PIN,r);
  analogWrite(RGB_GREEN_PIN,g);
  analogWrite(RGB_BLUE_PIN,b);
}