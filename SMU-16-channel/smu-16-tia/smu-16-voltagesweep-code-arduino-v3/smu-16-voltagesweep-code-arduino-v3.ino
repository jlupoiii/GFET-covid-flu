// This code file is Teensy Arduino code for measuring a voltage sweep for 
// the 16-channel self-designed SMU.

// Libraries used
#include <Wire.h>
#include <Adafruit_MCP4725.h>
#include <Adafruit_ADS1X15.h>

// Global variables used
Adafruit_MCP4725 dac_gate;
//Adafruit_MCP4725 dac_drain;
Adafruit_ADS1115 ads;

const int mux_pins_drain[4] = {0, 1, 2, 3};
const int num_channels_drain = 16;

float offset_voltage_tia = 1.5; // 1.5, positive value
float gate_start_voltage = -0.5; // minimum value is -1.5 [-1 * offset_voltage_tia]
float gate_end_voltage = 1.5; // maximum value is 1.8 [-1 * offset_voltage_tia + 3.3]
float R_f = 15000; // negative feedback resistor for transimpedance aplifier
float start_time_s;

const float sweep_delay_ms = 100; // 0.1s=100ms
const float mux_delay_ms = 10; // 0.01s=10ms
const int sweep_num_steps = (int)((gate_end_voltage - gate_start_voltage) * 100); // 100 times as many points, per volt, so 1V/100=10mV per division regardless of end voltage
int step_number = 0; // keeps track of current sweep step

/////////////////////////////////////////////////////////////////////


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

void set_gate_voltage(float voltage_unoffset) {
  float voltage_offset = constrain(voltage_unoffset + offset_voltage_tia, 0, 3.3);
  uint16_t value = (uint16_t)((voltage_offset) / 3.3 * 4095);
  dac_gate.setVoltage(value, false);
}


/////////////////////////////////////////////////////////////////////

//// Setup
//void setup() {
//  Serial.begin(115200);
//  Wire.begin();
//
//  // Initialize multiplexer pins for drain and gate sensors
//  for (int i = 0; i < 4; i++) {
//    pinMode(mux_pins_drain[i], OUTPUT);
//  }
//  
//  // Initialize I2C wires for ADC and two DACs
//  dac_gate.begin(0x65, &Wire);
//  ads.begin(0x48, &Wire);
//  ads.setGain(GAIN_TWO);
//
//  select_drain_mux_channel(0);
//
//  // Set start gate voltage
//  set_gate_voltage(gate_start_voltage);
//
//  // Wait for serial connection, and wait until Python sends "start", to begin the teensy code
//  while (!Serial);
//  while (true) {
//    if (Serial.available()) {
//      String cmd = Serial.readStringUntil('\n');
//      if (cmd == "start") {
//        break;
//      }
//    }
//  }
//
//  
//  }

///////////////////////////////////////////////////////////////////////


//// Loop
//void loop() {
//  // Stop loop once we’ve reached the final step
//  if (step_number >= sweep_num_steps) {
//    Serial.println("DONE");
//    return;
//  }
//  if (step_number==0) {
//    start_time_s = millis() / 1000.0;
//  }
//
////   Log the step number(frame num), time elapsed since the start of the test, and the drain voltage (constant)
//  Serial.print(step_number);
//  Serial.print(", ");
//  Serial.print(millis()/1000.0 - start_time_s, 3);
//  Serial.print(", ");
//
//  // calculate gate voltage based on the step number, set the gate voltage, and log it
//  float gate_voltage = gate_start_voltage + (gate_end_voltage - gate_start_voltage) * (float(step_number) / sweep_num_steps);
//  set_gate_voltage(gate_voltage);
//  Serial.print(gate_voltage, 2);
////  Serial.print(", ");
//
//  // delay between gate voltage sweeps, to let the new gate voltage settle
//  delay(sweep_delay_ms);
//
//
////  float opamp_output_voltage =  read_adc(0);
////  float current = (offset_voltage_tia - opamp_output_voltage) / R_f; // for R_f, negative feedback resistor
////  Serial.print(current, 10);
////  Serial.println(", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0");
//
//
//  // Read all 16 mux channels
//  for (int ch = 0; ch < num_channels_drain; ch++) {
//    
//    select_drain_mux_channel(ch);
//    
//    // let signal between mux channels settle with small delay
//    delay(mux_delay_ms);
//    
//    float opamp_output_voltage =  read_adc(0);
//    float current = (offset_voltage_tia - opamp_output_voltage) / R_f; // for R_f, negative feedback resistor
//
//    Serial.print(", ");
//    Serial.print(current, 12); // replace this with the current reading
////    Serial.print(opamp_output_voltage, 4); // replace this with the voltage reading
//  }
//  Serial.println("");
//
//  step_number++;  // Move to next voltage step
//}


///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////

bool sweeping = false;

// Setup
void setup() {
  Serial.begin(115200);
//  Serial.setTimeout(5);      // <-- put it HERE
  Wire.begin();
//  last_command_ms = millis();

  // Initialize multiplexer pins for drain and gate sensors
  for (int i = 0; i < 4; i++) {
    pinMode(mux_pins_drain[i], OUTPUT);
  }
  
  // Initialize I2C wires for ADC and two DACs
  dac_gate.begin(0x65, &Wire);
  ads.begin(0x48, &Wire);
  ads.setGain(GAIN_TWO);

  select_drain_mux_channel(0);

  // Set start gate voltage
  set_gate_voltage(gate_start_voltage);
}




// Loop
void loop() {

  // Check for Python command
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "start") {
      sweeping = true;
      step_number = 0;        // reset step count for new sweep
      start_time_s = millis() / 1000.0;
    } else if (cmd == "stop") {
      sweeping = false;
    }
  }

  if (!sweeping) return;


  
  // Stop loop once we’ve reached the final step
  if (step_number >= sweep_num_steps) {
    Serial.println("DONE");
    return;
  }
  if (step_number==0) {
    start_time_s = millis() / 1000.0;
  }

//   Log the step number(frame num), time elapsed since the start of the test, and the drain voltage (constant)
  Serial.print(step_number);
  Serial.print(", ");
  Serial.print(millis()/1000.0 - start_time_s, 3);
  Serial.print(", ");

  // calculate gate voltage based on the step number, set the gate voltage, and log it
  float gate_voltage = gate_start_voltage + (gate_end_voltage - gate_start_voltage) * (float(step_number) / sweep_num_steps);
  set_gate_voltage(gate_voltage);
  Serial.print(gate_voltage, 2);
//  Serial.print(", ");

  // delay between gate voltage sweeps, to let the new gate voltage settle
  delay(sweep_delay_ms);


//  float opamp_output_voltage =  read_adc(0);
//  float current = (offset_voltage_tia - opamp_output_voltage) / R_f; // for R_f, negative feedback resistor
//  Serial.print(current, 10);
//  Serial.println(", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0");


  // Read all 16 mux channels
  for (int ch = 0; ch < num_channels_drain; ch++) {
    
    select_drain_mux_channel(ch);
    
    // let signal between mux channels settle with small delay
    delay(mux_delay_ms);
    
    float opamp_output_voltage =  read_adc(0);
    float current = (offset_voltage_tia - opamp_output_voltage) / R_f; // for R_f, negative feedback resistor

    Serial.print(", ");
    Serial.print(current, 12); // replace this with the current reading
//    Serial.print(opamp_output_voltage, 4); // replace this with the voltage reading
  }
  Serial.println("");

  step_number++;  // Move to next voltage step
}
