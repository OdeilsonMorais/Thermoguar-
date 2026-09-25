// TermoGuará v2 — Nano clássico ATmega328P, lógica 5 V.
#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>
#include <Adafruit_MAX31865.h>
#include <avr/wdt.h>
#include <math.h>
#include "Config.h"

// Requer Arduino AVR Boards >=1.8.6: API Wire.setWireTimeout.

const uint8_t GATE[2] = {5, 6};
const uint8_t ADS_ADDR[2] = {0x48, 0x49};
Adafruit_MAX31865 pt1(10), pt2(9);
Adafruit_MAX31865* pt[2] = {&pt1, &pt2};
// Bits: 1 NTC inválido, 2 PT inválido, 4 sobretemperatura,
// 8 divergência NTC, 16 comunicação, 32 aquisição atrasada.
struct Chamber {
  bool running;
  uint8_t fault, pwm;
  float sp, kp, ki, kd, integral, previous, derivative;
  uint32_t started, duration;
};
Chamber c[2] = {};
float temp[6] = {NAN,NAN,NAN,NAN,NAN,NAN};
uint8_t liveFault[2] = {};
uint32_t lastSample = 0, lastPing = 0, sequence = 0;
bool sampled = false, pingSeen = false;
char input[96];
uint8_t used = 0;
bool overflow = false;

void off(uint8_t i) {
  analogWrite(GATE[i], 0);
  c[i].running = false;
  c[i].pwm = 0;
  c[i].integral = c[i].derivative = 0;
}
void trip(uint8_t i, uint8_t reason) {
  off(i);
  c[i].fault |= reason;
}
void interlocks() {
  uint32_t now = millis();
  for (uint8_t i=0; i<2; ++i) {
    if (!c[i].running) continue;
    if (!pingSeen || uint32_t(now-lastPing)>LINK_TIMEOUT_MS) trip(i,16);
    else if (!sampled || uint32_t(now-lastSample)>1500) trip(i,32);
    else if (uint32_t(now-c[i].started)>=c[i].duration) off(i);
  }
}

bool readReg(uint8_t addr, uint8_t reg, uint16_t &value) {
  Wire.clearWireTimeoutFlag();
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission()!=0) return false;
  if (Wire.requestFrom(addr, uint8_t(2))!=2 || Wire.getWireTimeoutFlag()) return false;
  value = uint16_t(Wire.read())<<8;
  value |= Wire.read();
  return true;
}
// Conversão single-shot, ±6.144 V, 128 SPS; espera limitada mesmo se ADC falhar.
bool adc(uint8_t addr, uint8_t channel, float &volts) {
  uint16_t config = 0x8183 | (uint16_t(4+channel)<<12);
  Wire.clearWireTimeoutFlag();
  Wire.beginTransmission(addr);
  Wire.write(1); Wire.write(config>>8); Wire.write(config & 0xff);
  if (Wire.endTransmission()!=0 || Wire.getWireTimeoutFlag()) return false;
  uint32_t began = millis();
  uint16_t value;
  do {
    delay(1);
    interlocks();
    if (!readReg(addr,1,value)) return false;
    // Configuração lida deve coincidir; evita interpretar dados do dispositivo errado.
    if ((value & 0x7fff)!=(config & 0x7fff)) return false;
    if (value & 0x8000) {
      if (!readReg(addr,0,value)) return false;
      int16_t raw = int16_t(value);
      if (raw<0 || raw>=32760) return false;
      volts = raw * 0.0001875f;
      return true;
    }
  } while (uint32_t(millis()-began)<30);
  return false;
}
float corrected(float t, uint8_t i) {
  if (!isfinite(t) || t<MIN_VALID_C || t>MAX_VALID_C) return NAN;
  t = CAL_GAIN[i]*t + CAL_OFFSET[i];
  return isfinite(t) && t>=MIN_VALID_C && t<=MAX_VALID_C ? t : NAN;
}
void acquire() {
  for (uint8_t i=0; i<2; ++i) {
    float exc = NAN;
    bool supplyOk = adc(ADS_ADDR[i],2,exc) && exc>=2.8f && exc<=3.5f;
    for (uint8_t j=0; j<2; ++j) {
      uint8_t n = 2*i+j;
      float v;
      temp[n] = NAN;
      if (supplyOk && adc(ADS_ADDR[i],j,v) && v>0.01f*exc && v<0.99f*exc) {
        // 3.3V -- Rfixo -- AIN -- NTC -- GND.
        float r = SERIES_R[n]*v/(exc-v);
        float t = 1.0f/(1.0f/298.15f + log(r/NTC_R25[n])/NTC_BETA[n])-273.15f;
        temp[n] = corrected(t,n);
      }
    }
    uint16_t raw = pt[i]->readRTD();
    uint8_t fault = pt[i]->readFault();
    temp[4+i] = (fault || raw==0 || raw>=32767) ? NAN :
      corrected(pt[i]->calculateTemperature(raw,1000,PT_RREF[i]),4+i);
    interlocks();
    uint8_t f = 0;
    if (!isfinite(temp[2*i]) || !isfinite(temp[2*i+1])) f |= 1;
    if (!isfinite(temp[4+i])) f |= 2;
    if (temp[2*i]>=MAX_TEMP_C || temp[2*i+1]>=MAX_TEMP_C || temp[4+i]>=MAX_TEMP_C) f |= 4;
    if (!(f&1) && fabs(temp[2*i]-temp[2*i+1])>MAX_NTC_DELTA_C) f |= 8;
    liveFault[i] = f;
    if (f) trip(i,f); // Falhas ficam retidas até CLR; não há reinício automático.
  }
}
void control(uint8_t i, float dt) {
  if (!c[i].running) return;
  float pv = (temp[2*i]+temp[2*i+1])*0.5f;
  float error = c[i].sp-pv;
  float d = (pv-c[i].previous)/dt;
  c[i].derivative += dt/(2.0f+dt)*(d-c[i].derivative);
  c[i].previous = pv;
  float proposed = c[i].integral+c[i].ki*error*dt;
  float output = c[i].kp*error+proposed-c[i].kd*c[i].derivative;
  // Integração condicional anti-windup, inclusive para saída somente de aquecimento.
  if ((output>=0 && output<=MAX_PWM) || (output>MAX_PWM && error<0) || (output<0 && error>0))
    c[i].integral = constrain(proposed, -float(MAX_PWM), float(MAX_PWM));
  output = c[i].kp*error+c[i].integral-c[i].kd*c[i].derivative;
  c[i].pwm = uint8_t(constrain(output,0.0f,float(MAX_PWM)));
  analogWrite(GATE[i],c[i].pwm);
}
void telemetry() {
  Serial.print(F("DATA,1,")); Serial.print(sequence++);
  Serial.print(','); Serial.print(millis());
  for (uint8_t i=0;i<6;++i) { Serial.print(','); Serial.print(temp[i],3); }
  for (uint8_t i=0;i<2;++i) { Serial.print(','); Serial.print(c[i].sp,3); }
  for (uint8_t i=0;i<2;++i) { Serial.print(','); Serial.print(c[i].pwm); }
  for (uint8_t i=0;i<2;++i) { Serial.print(','); Serial.print(c[i].running ? 1 : 0); }
  for (uint8_t i=0;i<2;++i) { Serial.print(','); Serial.print(c[i].fault); }
  Serial.print(','); Serial.print(HARDWARE_VERIFIED ? 1 : 0);
  for (uint8_t i=0;i<2;++i) {
    uint32_t elapsed = uint32_t(millis()-c[i].started);
    uint32_t remaining = c[i].running && elapsed<c[i].duration ? (c[i].duration-elapsed)/1000 : 0;
    Serial.print(','); Serial.print(remaining);
  }
  Serial.println();
}
bool number(const char* s, float &v) {
  if (!s || !*s) return false;
  char* end;
  v = strtod(s,&end);
  return *end==0 && isfinite(v);
}
void reply(const char* id, const __FlashStringHelper* result, bool ok) {
  Serial.print(ok ? F("ACK,") : F("ERR,")); Serial.print(id);
  Serial.print(','); Serial.println(result);
}
void command() {
  // Separador preserva campos vazios para rejeitar quadros incompletos.
  char* tok[10]; uint8_t n=1; tok[0]=input;
  for (char* p=input; *p; ++p) if (*p==',') {
    *p=0; if (n>=10) { reply("0",F("FORMAT"),false); return; }
    tok[n++]=p+1;
  }
  float idNumber;
  if (n<2 || !number(tok[1],idNumber) || idNumber<1 || idNumber>65535 || idNumber!=floor(idNumber)) {
    reply("0",F("ID"),false); return;
  }
  const char* id=tok[1];
  if (!strcmp(tok[0],"HELLO") && n==2) {
    Serial.print(F("INFO,")); Serial.print(id); Serial.println(F(",THERMOGUARA,1")); return;
  }
  if (!strcmp(tok[0],"PING") && n==2) {
    lastPing=millis(); pingSeen=true; reply(id,F("PING"),true); return;
  }
  if (!strcmp(tok[0],"STOP") && n==2) {
    off(0); off(1); reply(id,F("STOP"),true); return;
  }
  float ch;
  if (n<3 || !number(tok[2],ch) || (ch!=1 && ch!=2)) { reply(id,F("CHANNEL"),false); return; }
  uint8_t i=uint8_t(ch)-1;
  if (!strcmp(tok[0],"OFF") && n==3) { off(i); reply(id,F("OFF"),true); return; }
  if (!strcmp(tok[0],"CLR") && n==3) {
    if (c[i].running || !sampled || liveFault[i] || uint32_t(millis()-lastSample)>1000 ||
        temp[2*i]>MAX_TEMP_C-5 || temp[2*i+1]>MAX_TEMP_C-5 || temp[4+i]>MAX_TEMP_C-5) {
      reply(id,F("NOT_SAFE"),false); return;
    }
    c[i].fault=0; reply(id,F("CLR"),true); return;
  }
  if (strcmp(tok[0],"START") || n!=8) { reply(id,F("FORMAT"),false); return; }
  float sp,kp,ki,kd,seconds;
  if (!number(tok[3],sp) || !number(tok[4],kp) || !number(tok[5],ki) ||
      !number(tok[6],kd) || !number(tok[7],seconds) || sp<MIN_SETPOINT_C || sp>MAX_SETPOINT_C ||
      kp<=0 || kp>100 || ki<0 || ki>20 || kd<0 || kd>100 || seconds<1 || seconds>MAX_RUN_S) {
    reply(id,F("RANGE"),false); return;
  }
  if (!HARDWARE_VERIFIED) { reply(id,F("CONFIG_REQUIRED"),false); return; }
  if (c[i].running || c[i].fault || !sampled || uint32_t(millis()-lastSample)>1000 ||
      !pingSeen || uint32_t(millis()-lastPing)>1500) { reply(id,F("NOT_READY"),false); return; }
  c[i].sp=sp; c[i].kp=kp; c[i].ki=ki; c[i].kd=kd;
  c[i].integral=c[i].derivative=0;
  c[i].previous=(temp[2*i]+temp[2*i+1])*0.5f;
  c[i].started=millis(); c[i].duration=uint32_t(seconds*1000);
  c[i].running=true;
  reply(id,F("START"),true);
}
void serialInput() {
  // Orçamento por loop impede inundação serial de atrasar as proteções.
  uint8_t budget=64;
  while (budget-- && Serial.available()) {
    char b=Serial.read();
    if (b=='\n') {
      if (overflow) { off(0); off(1); reply("0",F("OVERFLOW"),false); }
      else if (used) { input[used]=0; command(); }
      used=0; overflow=false;
    } else if (b!='\r') {
      if (used<sizeof(input)-1 && !overflow) input[used++]=b;
      else overflow=true;
    }
  }
}
void setup() {
  MCUSR=0; wdt_disable();
  for (uint8_t i=0;i<2;++i) { digitalWrite(GATE[i],LOW); pinMode(GATE[i],OUTPUT); off(i); }
  Serial.begin(115200);
  Wire.begin(); Wire.setClock(100000); Wire.setWireTimeout(25000,true);
  // Os dois CS devem estar inativos antes de qualquer acesso SPI.
  pinMode(10,OUTPUT); digitalWrite(10,HIGH);
  pinMode(9,OUTPUT); digitalWrite(9,HIGH);
  for (uint8_t i=0;i<2;++i) { pt[i]->begin(MAX31865_2WIRE); pt[i]->enable50Hz(false); }
  if (USE_WATCHDOG) wdt_enable(WDTO_2S);
  Serial.println(F("BOOT,THERMOGUARA,1"));
}
void loop() {
  interlocks(); serialInput(); interlocks();
  uint32_t now=millis();
  if (!sampled || uint32_t(now-lastSample)>=SAMPLE_MS) {
    uint32_t previous=lastSample;
    acquire();
    uint32_t completed=millis();
    float dt=sampled ? uint32_t(completed-previous)/1000.0f : SAMPLE_MS/1000.0f;
    lastSample=completed; sampled=true;
    interlocks();
    for (uint8_t i=0;i<2;++i) control(i,dt);
    telemetry();
  }
  if (USE_WATCHDOG) wdt_reset();
}
