// Libraries used
#include <Wire.h>
#include <Adafruit_MCP4725.h>
#include <Adafruit_ADS1X15.h>

// Global variables used
Adafruit_MCP4725 dac_gate;
Adafruit_ADS1115 ads;

const int mux_pins_drain[4] = {0, 1, 2, 3};
const int num_channels_drain = 16;

float offset_voltage_tia = 1.5;     // TIA offset
float gate_fixed_voltage = 0.0;     // FIXED gate voltage (set on start)
float R_f = 15000;                  // TIA feedback resistor

float sweep_delay_ms = 100;         // sampling period
const float mux_delay_ms = 10;

bool sweeping = false;
bool run_started = false;
float start_time_s;


/////////////////////////////////////////////////////////////////////


void select_drain_mux_channel(int channel) {
  for (int i = 0; i < 4; i++) {
    digitalWrite(mux_pins_drain[i], (channel >> i) & 1);
  }
}

float read_adc(int pin_channel) {
  int16_t raw = ads.readADC_SingleEnded(pin_channel);
  return ads.computeVolts(raw);
}

void set_gate_voltage(float voltage_unoffset) {
  float voltage_offset = constrain(voltage_unoffset + offset_voltage_tia, 0, 3.3);
  uint16_t value = (uint16_t)((voltage_offset) / 3.3 * 4095);
  dac_gate.setVoltage(value, false);
}


/////////////////////////////////////////////////////////////////////


void setup() {
  Serial.begin(115200);
  Wire.begin();

  // Initialize multiplexer pins for drain and gate sensors
  for (int i = 0; i < 4; i++) {
    pinMode(mux_pins_drain[i], OUTPUT);
  }
  
  // Initialize I2C wires for ADC and two DACs
  dac_gate.begin(0x65, &Wire);
  ads.begin(0x48, &Wire);
  ads.setGain(GAIN_TWO);

  select_drain_mux_channel(0);
  
}


/////////////////////////////////////////////////////////////////////



void loop() {

  // -------- SERIAL COMMAND HANDLING --------
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.startsWith("start")) {
      sweeping = true;
      run_started = false; // this is not in the other code

      // Expected: start,<gate_voltage>,<delay_ms>
      int i1 = cmd.indexOf(',');
      int i2 = cmd.indexOf(',', i1 + 1);

      if (i1 > 0 && i2 > i1) {
        gate_fixed_voltage = cmd.substring(i1 + 1, i2).toFloat();
        sweep_delay_ms     = cmd.substring(i2 + 1).toFloat();
      }

      // Set gate voltage ONCE at start
      set_gate_voltage(gate_fixed_voltage);
    }

    else if (cmd == "stop") {
      sweeping = false;
      run_started = false;
    }
  }

  if (!sweeping) return;

  // -------- START TIME --------
  if (!run_started) {
    start_time_s = millis() / 1000.0;
    run_started = true;
  }

  // -------- LOG TIME --------
  Serial.print(millis() / 1000.0 - start_time_s, 3);

  // -------- READ ALL DRAIN CHANNELS --------
  for (int ch = 0; ch < num_channels_drain; ch++) {
    select_drain_mux_channel(ch);
    delay(mux_delay_ms);

    float opamp_output_voltage = read_adc(0);
    float current = (offset_voltage_tia - opamp_output_voltage) / R_f;

    Serial.print(", ");
    Serial.print(current, 12);
  }
  Serial.println("");

  // -------- SAMPLING DELAY --------
  delay(sweep_delay_ms);
}
