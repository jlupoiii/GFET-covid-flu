//// This code file is Teensy Arduino code for measuring a time sweep for 
//// the 16-channel self-designed SMU.

// Libraries used
#include <Wire.h>
#include <Adafruit_MCP4725.h>
#include <Adafruit_ADS1X15.h>

// Global variables used
Adafruit_MCP4725 dac_gate;
Adafruit_MCP4725 dac_drain;
Adafruit_ADS1115 ads;

const int mux_pins_drain[4] = {0, 1, 2, 3};
const int num_channels_drain = 16;

float drain_voltage_supply = 0.1; // (in volts)
float gate_voltage;
float start_time_s;

const float sweep_delay_ms = 100; // 0.1s=100ms
const float mux_delay_ms = 10; // 0.01s=10ms
int step_number = 0; // keeps track of current sweep step

///////////////////////////////////////////////////////////////////////


void select_drain_mux_channel(int channel) {
  for (int i = 0; i < 4; i++) {
    digitalWrite(mux_pins_drain[i], (channel >> i) & 1);
  }
}

float read_adc(int pin_channel) {
  int16_t raw = ads.readADC_SingleEnded(pin_channel);
  float voltage = ads.computeVolts(raw);
  return voltage;
}

//void set_gate_voltage(float voltage) {
//  voltage = constrain(voltage, 0, 3.3);
//  uint16_t value = (uint16_t)(voltage / 3.3 * 4095);
//  dac_gate.setVoltage(value, false);
//}


///////////////////////////////////////////////////////////////////////


// Setup
void setup() {
  Serial.begin(115200);

  while (!Serial); // wait for USB serial connection to be established

  String inputString = "";
  while (true) {
    if (Serial.available()) {
      char inChar = Serial.read();
      if (inChar == '\n') {
        gate_voltage = inputString.toFloat();
        break;
      } else {
        inputString += inChar;
      }
    }
  }

  Wire.begin();

  // Initialize multiplexer pins for drain and gate sensors
  for (int i = 0; i < 4; i++) {
    pinMode(mux_pins_drain[i], OUTPUT);
  }

  // Initialize I2C wires for ADC and two DACs
  dac_gate.begin(0x65, &Wire);
  dac_drain.begin(0x64, &Wire);
  ads.begin(0x48, &Wire);
  ads.setGain(GAIN_TWO);

  // Set constant drain voltage
  uint16_t drain_digital_value = (uint16_t)(drain_voltage_supply / 3.3 * 4095);
  dac_drain.setVoltage(drain_digital_value, false);

   // Set constant gate voltage
  uint16_t gate_digital_value = (uint16_t)(gate_voltage / 3.3 * 4095);
  dac_gate.setVoltage(gate_digital_value, false);

  // Wait for serial connection, and wait until Python sends "start", to begin the teensy code
  while (!Serial);
  while (true) {
    if (Serial.available()) {
      String cmd = Serial.readStringUntil('\n');
      if (cmd == "start") {
        break;
      }
    }
  }

}


/////////////////////////////////////////////////////////////////////////


//// Loop
void loop() {

  if (step_number==0) {
    start_time_s = millis() / 1000.0;
  }

  // Log the step number(frame num), time elapsed since the start of the test, and the drain voltage (constant)
  Serial.print(step_number);
  Serial.print(", ");
  Serial.print(millis()/1000.0 - start_time_s, 3);
  Serial.print(", ");
  Serial.print(drain_voltage_supply);
  Serial.print(", ");
  Serial.print(gate_voltage); // maybe limit to 2 decimals?

  // delay between step number, between each 16-channel sweep
  delay(sweep_delay_ms);

  // Read all 16 mux channels
  for (int ch = 0; ch < num_channels_drain; ch++) {
    select_drain_mux_channel(ch);
    
    // let signal between mux channels settle with small delay
    delay(mux_delay_ms);
    
    float drain_voltage = read_adc(0);
    float current = (drain_voltage_supply - drain_voltage) / 10000.0; // 10000.0 for 10KOhm resistor
    Serial.print(", ");
    Serial.print(current, 12); // replace this with the current reading
  }

  Serial.println("");
  step_number++;  // Move to next time step
}
