#include <Adafruit_MAX31856.h> 
#include <SPI.h>

#define MAX31856_CS1 10
#define MAX31856_CS2 9

// Define os pinos dos Mosfets
#define MOSFET_1 5 
#define MOSFET_2 6 

Adafruit_MAX31856 max31856_1 = Adafruit_MAX31856(MAX31856_CS1);
Adafruit_MAX31856 max31856_2 = Adafruit_MAX31856(MAX31856_CS2);

void setup() {
  Serial.begin(9600);
  
  // Configura os pinos como saída e garante que comecem desligados
  pinMode(MOSFET_1, OUTPUT);
  pinMode(MOSFET_2, OUTPUT);
  digitalWrite(MOSFET_1, LOW);
  digitalWrite(MOSFET_2, LOW);

  while (!Serial);

  if (!max31856_1.begin()) Serial.println("Erro ao iniciar o MAX31856 (sensor 1)");
  if (!max31856_2.begin()) Serial.println("Erro ao iniciar o MAX31856 (sensor 2)");

  max31856_1.setThermocoupleType(MAX31856_TCTYPE_K);
  max31856_2.setThermocoupleType(MAX31856_TCTYPE_K);
}

void loop() {
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();

    if (comando == "R") {
      float t1 = max31856_1.readThermocoupleTemperature();
      float t2 = max31856_2.readThermocoupleTemperature();

      if (isnan(t1) || isnan(t2)) {
        Serial.println("NaN,NaN");
      } else {
        Serial.print(t1, 2);
        Serial.print(",");
        Serial.println(t2, 2);
      }
    } 
    // Comandos de aquecimento
    else if (comando == "ON") {
      digitalWrite(MOSFET_1, HIGH);
      digitalWrite(MOSFET_2, HIGH);
      Serial.println("AQUECIMENTO_LIGADO");
    } 
    else if (comando == "OFF") {
      digitalWrite(MOSFET_1, LOW);
      digitalWrite(MOSFET_2, LOW);
      Serial.println("AQUECIMENTO_DESLIGADO");
    }
  }
}