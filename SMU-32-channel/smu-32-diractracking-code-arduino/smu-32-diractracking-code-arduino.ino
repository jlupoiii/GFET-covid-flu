/* 32-CHANNEL CURRENT MEASUREMENT SMU
  --------
  HARDWARE
  --------

  Teensy 4.0
    
  GATE DAC:
    MCP4725
    SDA -> Teensy pin 18
    SCL -> Teensy pin 19

  ADC:
    LTC1867LCGN, 16-bit, 8-channel ADC

    LTC1867 SDI      -> Teensy pin 11 (MOSI)
    LTC1867 SDO      -> Teensy pin 12 (MISO)
    LTC1867 SCK      -> Teensy pin 13 (SCK)
    LTC1867 CS/CONV  -> Teensy pin 10

  MUX CONTROL:
    MAX4618 A -> Teensy pin 6
    MAX4618 B -> Teensy pin 7

  ANALOG ARCHITECTURE:
    4 x MAX4618
    Each MAX4618 = 2 independent 1:4 MUXes
    Total = 8 independent 1:4 MUXes

    2 x OPA4350
    Each OPA4350 = 4 op amps
    Total = 8 TIAs

    Each MUX output -> one TIA -> one LTC1867 ADC input

  CHANNEL MAPPING:
    
    MUX state 0:
      ADC/MUX 0 -> physical CH 0
      ADC/MUX 1 -> physical CH 4
      ADC/MUX 2 -> physical CH 8
      ADC/MUX 3 -> physical CH 12
      ADC/MUX 4 -> physical CH 16
      ADC/MUX 5 -> physical CH 20
      ADC/MUX 6 -> physical CH 24
      ADC/MUX 7 -> physical CH 28
    MUX state 1:
      ADC/MUX 0 -> physical CH 1
      ADC/MUX 1 -> physical CH 5
      ...
      ADC/MUX 7 -> physical CH 29
    MUX state 2:
      ADC/MUX 0 -> physical CH 2
      ADC/MUX 1 -> physical CH 6
      ...
      ADC/MUX 7 -> physical CH 30
    MUX state 3:
      ADC/MUX 0 -> physical CH 3
      ADC/MUX 1 -> physical CH 7
      ...
      ADC/MUX 7 -> physical CH 31

    General formula:
      physical_channel = 4 * adc_channel + mux_state

  ---------------
  SERIAL COMMANDS
  ---------------
  START COMMAND: start,Vstart,Vend,sweep_delay_ms,points_per_volt
    Example: start,-0.5,1.0,0,500
  STOP COMMAND: stop

  -------------
  SERIAL OUTPUT
  -------------
    step_number,
    elapsed_time_seconds,
    gate_voltage,
    current_CH0,
    current_CH1,
    ...
    current_CH31
*/

// libraries
#include <Wire.h>
#include <SPI.h>
#include <Adafruit_MCP4725.h>

// hardware objects, I2C
Adafruit_MCP4725 dac_gate;


// ========================
// DEFINE PINS
// ========================

// MCP4725, I2C
const int I2C_SDA_PIN = 18;
const int I2C_SCL_PIN = 19;

// LTC1867, SPI 
// MOSI = 11
// MISO = 12
// SCK  = 13
// CS   = 10
const int ADC_MOSI_PIN = 11;
const int ADC_MISO_PIN = 12;
const int ADC_SCK_PIN  = 13;
const int ADC_CS_PIN   = 10;

// MAX4618 MUX CONTROL
const int MUX_A_PIN = 6;
const int MUX_B_PIN = 7;


// ================================================================
// SYSTEM CONSTANTS
// ================================================================

// channel counts
const int NUM_ADC_CHANNELS = 8;
const int NUM_MUX_STATES   = 4;
const int NUM_CHANNELS     = 32;

// reference voltage
const float VREF = 1.2;

// TIA R_F
const float R_F = 8200.0;  // 8.2 kOhm

// GATE DAC
const float DAC_FULL_SCALE_VOLTAGE = 3.3;
const uint16_t DAC_MAX_CODE = 4095;

// LTC1867
// LTC1867 is a 16-bit ADC: 2^16 = 65536, subtract 1 to get 65535
// External ADC reference: VREF = shared 1.2 V precision reference
//   ADC code 0     ≈ 0 V
//   ADC code 65535 ≈ 1.2 V
const uint32_t ADC_MAX_CODE = 65535;

// SPI clock. LTC1867 allows high SCK frequencies, but starting conservatively is useful during bring-up.
const uint32_t ADC_SPI_CLOCK_HZ = 1000000;

// LTC1867 conversion time. Datasheet maximum conversion time is approximately 3.5 us. We use 5 us for margin.
const uint32_t ADC_CONVERSION_TIME_US = 5;

// ADC delay between measurements
// The LTC1867 needs acquisition time between conversions. 
// This is not normally necessary at these relatively slow 
// SMU measurement rates, but is left explicitly configurable.
const uint32_t ADC_ACQUIRE_US = 2;


// ================================================================
// SWEEP VARIABLES
// ================================================================

float gate_start_voltage = 0.0;
float gate_end_voltage   = 1.0;

//// settling delay time for both multiplexer and gate DAC
const uint32_t MUX_SETTLE_US = 1000; // automatically delays this amount, no matter what!!
const uint32_t GATE_SETTLE_MS = 10;
float sweep_delay_ms = 0.0; // additional delay on top of MUX_SETTLE_US

int gate_voltage_res = 500;
int sweep_num_steps  = 0;
int step_number = 0;
float start_time_s = 0.0;

bool sweeping = false;
bool run_started = false;

// ================================================================
// MEASUREMENT STORAGE
// ================================================================

// Stores the final current values.
// Index:
//   current[0]  = physical channel 0
//   current[1]  = physical channel 1
//   ...
//   current[31] = physical channel 31
//
float current[NUM_CHANNELS];

// Stores raw ADC results for debugging / future use.
uint16_t adc_raw[NUM_ADC_CHANNELS];


// Stores converted ADC voltages for debugging / future use.
float adc_voltage[NUM_ADC_CHANNELS];

// ================================================================
// FUNCTION DECLARATIONS
// ================================================================

void select_mux_state(int state);

void set_gate_voltage(float voltage_unoffset);

uint8_t build_ltc1867_config(int channel);

uint16_t read_ltc1867_channel(int channel);

float raw_to_voltage(uint16_t raw);

float voltage_to_current(float voltage);

void measure_all_32_channels();

void print_measurement_frame(float gate_voltage);

bool parse_start_command(String cmd);



// ================================================================
// DEFINING FUNCTIONS
// ================================================================

// MUX CONTROL
/*
  Select one of four global MUX states (0, 1, 2, 3). All eight independent 1:4 MUXes switch together.
  This code assumes:
    state 0 -> A=0, B=0
    state 1 -> A=1, B=0
    state 2 -> A=0, B=1
    state 3 -> A=1, B=1
*/

void select_mux_state(int state)
{
  state = constrain(state, 0, 3);
  digitalWrite(MUX_A_PIN, state & 0x01);
  digitalWrite(MUX_B_PIN, (state >> 1) & 0x01);
}


// GATE VOLTAGE
/*
  Set effective gate voltage, VREF=1.2V is offset, so V_GATE = V_DAC - VREF
      Minimum gate voltage: 0.0 - 1.2 = -1.2 V
      Maximum gate voltage: 3.3 - 1.2 = +2.1 V
*/
void set_gate_voltage(float voltage_unoffset)
{
  float voltage_offset = voltage_unoffset + VREF;

  voltage_offset = constrain(
    voltage_offset,
    0.0,
    DAC_FULL_SCALE_VOLTAGE
  );

  uint16_t dac_code = (uint16_t)(
    (voltage_offset / DAC_FULL_SCALE_VOLTAGE)
    * DAC_MAX_CODE
    + 0.5 // add 0.5 here to abide by '5 or more raise the score 4 or less let it rest'
  );

  dac_gate.setVoltage(dac_code, false);
}


// LTC1867 CONFIGURATION WORD
/*
  LTC1867 7-bit configuration word:
    SD OS S1 S0 COM UNI SLP

  For our configuration:
    SD  = 1
      Single-ended input
    OS/S1/S0
      Select ADC channel 0 through 7, in binary
    COM = 0
      CH7 is used as a normal channel
    UNI = 1
      Unipolar conversion
    SLP = 0
      Automatic nap mode, not sleep mode

  Channel encoding:
                SD OS S1 S0 COM UNI SLP
    Channel 0:  1  0  0  0   0   1   0
    Channel 1:  1  1  0  0   0   1   0
    Channel 2:  1  0  0  1   0   1   0
    Channel 3:  1  1  0  1   0   1   0
    Channel 4:  1  0  1  0   0   1   0
    Channel 5:  1  1  1  0   0   1   0
    Channel 6:  1  0  1  1   0   1   0
    Channel 7:  1  1  1  1   0   1   0
*/

// congifuration, preapares the ADC for the state to read from a specific channel
uint8_t build_ltc1867_config(int channel)
{
  channel = constrain(channel, 0, 7);

  uint8_t SD  = 1;
  uint8_t OS  = channel & 0x01;
  uint8_t S1  = (channel >> 2) & 0x01;
  uint8_t S0  = (channel >> 1) & 0x01;
  uint8_t COM = 0;
  uint8_t UNI = 1;
  uint8_t SLP = 0;

  uint8_t config =
      (SD  << 6)
    | (OS  << 5)
    | (S1  << 4)
    | (S0  << 3)
    | (COM << 2)
    | (UNI << 1)
    | (SLP << 0);

  return config;
}


// LTC1867 ADC READ
/*
  Read one LTC1867 ADC channel.

  LTC1867 operation:

  1. CS/CONV rising edge starts a conversion.
  2. Wait for conversion to finish.
  3. Bring CS/CONV LOW.
  4. Shift out the completed 16-bit conversion.
  5. Simultaneously shift in the 7-bit configuration for
     the NEXT conversion.
  6. Return CS/CONV HIGH.

  IMPORTANT PIPELINE NOTE:

  The LTC1867 configuration sent during one serial read
  configures the NEXT conversion.

  Therefore, this driver performs one conversion with the
  requested channel already configured.

  During startup, initialize_ltc1867() performs dummy
  conversions to establish the pipeline.
*/


uint16_t read_ltc1867_channel(int channel)
{
  channel = constrain(channel, 0, 7);
  uint8_t config = build_ltc1867_config(channel); // make config set of numbers to set to device for speific channel measurement

  // this is a mock measurement to establish pipeline:
  // Start conversion: LTC1867 starts conversion on rising edge of CS/CONV.
  digitalWrite(ADC_CS_PIN, LOW);      // set low to make sure it's low initially, bc conversion is done on rising edge of CS/CONV
  delayMicroseconds(ADC_ACQUIRE_US);  // delay before setting high
  digitalWrite(ADC_CS_PIN, HIGH);     // set high
  delayMicroseconds(ADC_CONVERSION_TIME_US);  // delay before next measurement


  /*
    Serial read.
    Pull CS low to enable serial interface.
    We clock 16 bits total.
    The first 7 bits transmitted on MOSI contain the LTC1867 configuration word.
    We left-align the 7-bit configuration into a 16-bit word:
      config bit 6 -> transmitted first
      ...
      config bit 0
    Remaining bits are zero
  */
  uint16_t config_word = ((uint16_t)config) << 9; // convert into 16-bits

  SPI.beginTransaction(
    SPISettings(
      ADC_SPI_CLOCK_HZ,
      MSBFIRST,
      SPI_MODE0
    )
  );
  digitalWrite(ADC_CS_PIN, LOW); // set low because must start low
  uint16_t result = SPI.transfer16(config_word); // acquire digital 16-bit measurement
  digitalWrite(ADC_CS_PIN, HIGH); // set high
  SPI.endTransaction();

  return result;
}


// ADC CODE -> VOLTAGE, converts 16-bit code into readable voltage
// LTC1867 unipolar 16-bit mode: code 0 = approx 0 V, code 65535 = approx full-scale voltage
float raw_to_voltage(uint16_t raw)
{
  return (
    ((float)raw / (float)ADC_MAX_CODE)
    * VREF
  );
}


// TIA VOLTAGE -> CURRENT, converts ADC voltage into current based on transimpedance amplifier resistor value
  // TIA transfer relationship: I = (VREF - V_TIA_OUT) / R_F
  // VREF = 1.2 V
  // R_F  = 8.2 kOhm
  // At zero current: V_TIA_OUT = 1.2 V      ---->       I = 0 A
float voltage_to_current(float voltage)
{
  return (VREF - voltage) / R_F;
}


// INITIALIZE LTC1867, because first conversion after power-up can be invalid
/*
  Initialize the LTC1867 conversion pipeline.
  The datasheet specifies that after power-up, the first
  conversion can be invalid.
  We perform dummy reads to establish the ADC state.
*/

void initialize_ltc1867()
{
  digitalWrite(ADC_CS_PIN, LOW);
  delayMicroseconds(ADC_ACQUIRE_US);
  digitalWrite(ADC_CS_PIN, HIGH); // Rising edge starts first dummy conversion.
  delayMicroseconds(ADC_CONVERSION_TIME_US);

  // Read/discard first conversion and configure CH0.
  SPI.beginTransaction(
    SPISettings(
      ADC_SPI_CLOCK_HZ,
      MSBFIRST,
      SPI_MODE0
    )
  );
  digitalWrite(ADC_CS_PIN, LOW);
  SPI.transfer16(
    ((uint16_t)build_ltc1867_config(0)) << 9
  );
  digitalWrite(ADC_CS_PIN, HIGH);
  SPI.endTransaction();


  // Second dummy conversion to establish CH0.
  read_ltc1867_channel(0);
}


// MEASURE ALL 32 CHANNELS, function
/*
  Measurement order:

    MUX state 0:
      ADC0 -> CH0
      ADC1 -> CH4
      ADC2 -> CH8
      ADC3 -> CH12
      ADC4 -> CH16
      ADC5 -> CH20
      ADC6 -> CH24
      ADC7 -> CH28

    MUX state 1:
      ADC0 -> CH1
      ADC1 -> CH5
      ...
      ADC7 -> CH29
    MUX state 2:
      ADC0 -> CH2
      ADC1 -> CH6
      ...
      ADC7 -> CH30
    MUX state 3:
      ADC0 -> CH3
      ADC1 -> CH7
      ...
      ADC7 -> CH31
  Formula:
      physical_channel = 4 * adc_channel + mux_state
*/

void measure_all_32_channels()
{
   // loop over the 4 MUX states (0,1,2,3)
  for (int mux_state = 0;
       mux_state < NUM_MUX_STATES;
       mux_state++)
  {
    // Select all 8 MUXes simultaneously.
    select_mux_state(mux_state);

    // Allow MAX4618 / analog circuitry / TIA to settle.
    delayMicroseconds(MUX_SETTLE_US);


    // Read all 8 ADC inputs.
    for (int adc_channel = 0;
         adc_channel < NUM_ADC_CHANNELS;
         adc_channel++)
    {
      /*
        First read establishes/configures requested channel.
        Because the LTC1867 pipelines its channel configuration,
        we perform a discard conversion first.
        Second conversion gives the actual measurement after
        the requested channel has been configured.
      */
      read_ltc1867_channel(adc_channel);
      uint16_t raw = read_ltc1867_channel(adc_channel);

      float voltage = raw_to_voltage(raw); // Convert ADC code to voltage.
      int physical_channel = 4 * adc_channel + mux_state; // Calculate physical channel number.


      // Store results.
      adc_raw[adc_channel] = raw;
      adc_voltage[adc_channel] = voltage;
      current[physical_channel] = voltage_to_current(voltage);
    }
  }
}


// ================================================================
// PRINT ONE COMPLETE MEASUREMENT FRAME
// ================================================================


void print_measurement_frame(float gate_voltage)
{
  // Step number.
  Serial.print(step_number);
  Serial.print(", ");

  // Elapsed time.
  float elapsed_time_s = millis() / 1000.0 - start_time_s;
  Serial.print(elapsed_time_s, 3);
  Serial.print(", ");


  // Gate voltage.
  Serial.print(gate_voltage, 6);

  // All 32 currents.
  for (int channel = 0;
       channel < NUM_CHANNELS;
       channel++)
  {
    Serial.print(", ");
    Serial.print(current[channel], 12);
  }

  Serial.println();
}


// PARSE START COMMAND
  //Expected format: start,Vstart,Vend,sweep_delay_ms,points_per_volt

// returns true if it's a valid command, and extracts important variables
bool parse_start_command(String cmd)
{
  int i1 = cmd.indexOf(',');
  int i2 = cmd.indexOf(',', i1 + 1);
  int i3 = cmd.indexOf(',', i2 + 1);
  int i4 = cmd.indexOf(',', i3 + 1);

  if (
       i1 <= 0
    || i2 <= i1
    || i3 <= i2
    || i4 <= i3
  )
  {
    return false;
  }

  gate_start_voltage =  cmd.substring(i1 + 1, i2).toFloat();
  gate_end_voltage =    cmd.substring(i2 + 1, i3).toFloat();
  sweep_delay_ms =      cmd.substring(i3 + 1, i4).toFloat();
  gate_voltage_res =    cmd.substring(i4 + 1).toInt();

  // Basic input validation.
  if (gate_voltage_res <= 0)
  {
    return false;
  }

  if (gate_end_voltage <= gate_start_voltage)
  {
    return false;
  }


  // Enforce gate range based on DAC + shared VREF offset.
    // Minimum: 0 - VREF
    // Maximum: 3.3 - VREF
  const float MIN_GATE_VOLTAGE = -VREF;
  const float MAX_GATE_VOLTAGE = DAC_FULL_SCALE_VOLTAGE - VREF;


  if (
       gate_start_voltage < MIN_GATE_VOLTAGE
    || gate_start_voltage > MAX_GATE_VOLTAGE
    || gate_end_voltage   < MIN_GATE_VOLTAGE
    || gate_end_voltage   > MAX_GATE_VOLTAGE
  )
  {
    return false;
  }


  // Calculate number of intervals.
  //Round instead of simple truncation to reduce floating-point
  // issues.
  sweep_num_steps = (int)(
    (gate_end_voltage - gate_start_voltage)
    * gate_voltage_res
    + 0.5
  );


  if (sweep_num_steps <= 0)
  {
    return false;
  }

  return true;
}


// ================================================================
// SETUP
// ================================================================
void setup()
{
  // Serial
  Serial.begin(115200);

  // I2C
  Wire.begin();


  // MCP4725
  if (!dac_gate.begin(0x65, &Wire))
  {
    Serial.println("ERROR: MCP4725 not found");
  }

  // Start gate at 0 V effective gate voltage.
  set_gate_voltage(0.0);

  // MUX
  pinMode(MUX_A_PIN, OUTPUT);
  pinMode(MUX_B_PIN, OUTPUT);
  select_mux_state(0);

  // LTC1867, SPI protocol
  pinMode(ADC_CS_PIN, OUTPUT);
  digitalWrite(ADC_CS_PIN, HIGH); // Keep CS/CONV high when idle.
  SPI.begin(); // Initialize hardware SPI.
  // Initialize LTC1867.
  initialize_ltc1867();


  // Initialize current list/array
  for (int i = 0; i < NUM_CHANNELS; i++)
  {
    current[i] = 0.0;
  }

  // Startup message
  Serial.println("SMU32 IS FIRED UP");
}


// ================================================================
// LOOP
// ================================================================
void loop()
{
  // CHECK SERIAL COMMANDS
  if (Serial.available())
  {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    // START COMMAND FROM PYTHON/COMPUTER
    if (cmd.startsWith("start"))
    {
      bool valid = parse_start_command(cmd);

      if (valid)
      {
        sweeping = true;
        run_started = false;
        step_number = 0;

        Serial.println("STARTED");
      }
      else
      {
        Serial.println("ERROR: Invalid start command");
      }
    }


    // STOP COMMAND FROM PYTHON/COMPUTER
    else if (cmd == "stop")
    {
      sweeping = false;
      run_started = false; // don't set this to true until the elapsed timer has started
      step_number = 0;

      // Return gate to 0 V effective voltage.
      set_gate_voltage(0.0);

      Serial.println("STOPPED");
    }
  }


  // If not sweeping, do nothing else.
  if (!sweeping)
  {
    return;
  }


  // ==============================================================
  // CALCULATE CURRENT GATE VOLTAGE
  // ==============================================================

  float gate_voltage;
  /*
    Total sweep:
      Forward:
        step 0 -> sweep_num_steps
      Reverse:
        step sweep_num_steps + 1
        -> 2 * sweep_num_steps
  */

  if (step_number > 2 * sweep_num_steps)
  {
    Serial.println("DONE");
    sweeping = false;
    run_started = false;
    step_number = 0;

    // Return gate to 0 V after measurement.
    set_gate_voltage(0.0);

    return;
  }


  // FORWARD SWEEP
  if (step_number <= sweep_num_steps)
  {
    gate_voltage =
      gate_start_voltage
      + (gate_end_voltage - gate_start_voltage)
      * (
          (float)step_number
          / (float)sweep_num_steps
        );
  }


  // REVERSE SWEEP
  else
  {
    gate_voltage =
      gate_end_voltage
      - (gate_end_voltage - gate_start_voltage)
      * (
          (float)(step_number - sweep_num_steps)
          / (float)sweep_num_steps
        );
  }

  // SET GATE VOLTAGE
  set_gate_voltage(gate_voltage);

  // WAIT FOR GATE SETTLING
  delay(GATE_SETTLE_MS);


  // START TIMER IF NOT STARTED, and set run_started to true here
  if (!run_started)
  {
    start_time_s = millis() / 1000.0;
    run_started = true;
  }


  // MEASURE ALL 32 CHANNELS
  measure_all_32_channels();

  // PRINT COMPLETE FRAME
  print_measurement_frame(gate_voltage);


  // OPTIONAL ADDITIONAL SWEEP DELAY, inputted from python side and 'start' command line

  /*
    This delay is in addition to GATE_SETTLE_MS.

    If sweep_delay_ms is intended to represent the TOTAL delay
    after setting the gate, we should instead subtract the 10 ms
    gate-settling delay from it.

    Currently it behaves as an additional delay.
  */

  if (sweep_delay_ms > 0.0)
  {
    delay((uint32_t)sweep_delay_ms);
  }


  // NEXT SWEEP STEP, increment step counter
  step_number++;
}





























// old code below

















//// This code file is Teensy Arduino code for measuring a voltage sweep for 
//// the 32-channel self-designed SMU.
//
//// Libraries used
//#include <Wire.h>
//#include <Adafruit_MCP4725.h>
//#include <Adafruit_ADS1X15.h>
//
//// Global variables used
//Adafruit_MCP4725 dac_gate;
//Adafruit_ADS1115 ads;
//
//const int mux_pins_drain[4] = {0, 1, 2, 3};
//const int num_channels_drain = 16;
//
//float offset_voltage_tia = 1.5; //2.15; // 1.5, positive value // cannot change this value
//float gate_start_voltage = 0; // minimum value is -1.5 [-1 * offset_voltage_tia] // default value, will be overridden by python serial inuput
//float gate_end_voltage = 1.0; // maximum value is 1.8 [-1 * offset_voltage_tia + 3.3] // default value, will be overridden by python serial inuput
//float R_f = 15000; // negative feedback resistor for transimpedance aplifier
//
//float sweep_delay_ms = 0; // 0.05s=50ms           // PART OF DELAY CODE
//const float mux_delay_ms = 0; // 0.001s=1ms       // PART OF DELAY CODE
//int sweep_num_steps;
//int gate_voltage_res;
////int sweep_num_steps = (int)((gate_end_voltage - gate_start_voltage) * 500); // 500 times as many points, per volt, so 1V/500=2mV per division regardless of end voltage
//int step_number = 0; // keeps track of current sweep step
//
//bool sweeping = false; // true or false depeding on when measurements are actively being taken
//bool run_started = false; // for setting start time
//float start_time_s; // the time at which the measurements begin 
//
//
///////////////////////////////////////////////////////////////////////
//
//
//void select_drain_mux_channel(int channel) {
//  for (int i = 0; i < 4; i++) {
//    digitalWrite(mux_pins_drain[i], (channel >> i) & 1);
//  }
//}
//
//float read_adc(int pin_channel) {
//  int16_t raw = ads.readADC_SingleEnded(pin_channel);
//  float voltage = ads.computeVolts(raw);
//  return voltage;
//}
//
//void set_gate_voltage(float voltage_unoffset) {
//  float voltage_offset = constrain(voltage_unoffset + offset_voltage_tia, 0, 3.3);
//  uint16_t value = (uint16_t)((voltage_offset) / 3.3 * 4095);
//  dac_gate.setVoltage(value, false);
//}
//
//
///////////////////////////////////////////////////////////////////////
//
//
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
//}
//
//
//
//
//// Loop
//void loop() {
//
//  // Check for Python command
//  if (Serial.available()) {
//    String cmd = Serial.readStringUntil('\n');
//    cmd.trim();
//
//    if (cmd.startsWith("start")) {
//      sweeping = true;
//      step_number = 0;
//    
//      // Parse parameters
//      int i1 = cmd.indexOf(',');
//      int i2 = cmd.indexOf(',', i1 + 1);
//      int i3 = cmd.indexOf(',', i2 + 1);
//      int i4 = cmd.indexOf(',', i3 + 1);
//    
//      if (i1 > 0 && i2 > i1 && i3 > i2 && i4 > i3) {
//        gate_start_voltage = cmd.substring(i1 + 1, i2).toFloat();
//        gate_end_voltage   = cmd.substring(i2 + 1, i3).toFloat();
//        sweep_delay_ms     = cmd.substring(i3 + 1, i4).toFloat();
//        gate_voltage_res   = cmd.substring(i4 + 1).toFloat();
//        
//        sweep_num_steps = (int)((gate_end_voltage - gate_start_voltage) * gate_voltage_res);
//
//      }
//    
//    } else if (cmd == "stop") {
//      sweeping = false;
//      run_started = false;
//
//    }
//  }
//  if (!sweeping) return;
//  
//
//  // Stop loop once we’ve reached the final step
//  // calculate gate voltage based on the step number, set the gate voltage, and log it
//  // use clever math for forward vs reserve sweep
//  float gate_voltage;
//  if (step_number > 2*sweep_num_steps) {
//    Serial.println("DONE");
//    sweeping = false;
//    step_number = 0;
//    return;
//  } else if (step_number >= sweep_num_steps) {
//    gate_voltage = gate_end_voltage - (gate_end_voltage - gate_start_voltage) * (float(step_number - sweep_num_steps) / sweep_num_steps);
//  } else {
//    gate_voltage = gate_start_voltage + (gate_end_voltage - gate_start_voltage) * (float(step_number) / sweep_num_steps);
//  }  
//  // set the gate voltage
//  set_gate_voltage(gate_voltage);
//
//  // for keeping track of starting time
//  if (!run_started) {
//    start_time_s = millis()/1000.0;
//    run_started = true;
//  }
//
//  // Log the step number(frame num), time elapsed since the start of the test, the drain voltage (constant), and the gate voltage (sweeping)
//  Serial.print(step_number); 
//  Serial.print(", ");
//  Serial.print(millis()/1000.0 - start_time_s, 3);
//  Serial.print(", ");
//  Serial.print(gate_voltage, 6);
//
//
////  // delay between gate voltage sweeps, to let the new gate voltage settle    // PART OF DELAY CODE
////  delay(sweep_delay_ms);                                                      // PART OF DELAY CODE
//
//  // Read all 16 mux channels
//  for (int ch = 0; ch < num_channels_drain; ch++) {
//    
//    select_drain_mux_channel(ch);
//    
////    // let signal between mux channels settle with small delay                // PART OF DELAY CODE
////    delay(mux_delay_ms);                                                      // PART OF DELAY CODE
//    
//    float opamp_output_voltage =  read_adc(0);
//    float current = (offset_voltage_tia - opamp_output_voltage) / R_f; // for R_f, negative feedback resistor
//
//    Serial.print(", ");
//    Serial.print(current, 12);
//  }
//  Serial.println("");
//
//  step_number++;  // Move to next voltage step
//}
