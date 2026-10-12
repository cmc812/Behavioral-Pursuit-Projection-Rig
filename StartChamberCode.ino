/*
* door_controller.ino
*
* Stepper motor door controller for behavioral rig.
* TMC2209 via AltSoftSerial + AccelStepper.
*
* Key design principles:
*   - Serial handling is non-blocking (no readStringUntil)
*   - No Serial.println() during normal operation (prevents
*     output buffer backpressure when Bonsai doesn't read)
*   - No delay() in main loop (motor timing stays smooth)
*   - All state changes use millis()-based timing
*
* Serial commands (from Bonsai, 9600 baud):
*   2    — enable IR sensor mode
*   6    — open door
*   7    — close door
*   9    — emergency stop
*   0    — reset/idle
*   10   — nudge door forward 250 steps (Bonsai Shift+,)
*   11   — nudge door backward 250 steps (Bonsai Shift+.)
*   22   — easter egg (RGB cycle)
*   d    — toggle debug output on/off
*   S<n> — set steps per revolution (e.g. S2800 or S2222)
*
* TTL output (pin 7 → Open Ephys):
*   1 pulse  = door opening
*   2 pulses = door closing
*   3 pulses = emergency stop
*
* TTL output (pin 8 → Open Ephys):
*   Mirrors LED on/off during session & trial flashes
*
* Wiring:
*   Pin 4  → STEP
*   Pin 5  → DIR
*   Pin 6  → EN
*   Pin 3  → Toggle button (INPUT_PULLUP)
*   Pin 13 → IR sensor (LOW = detected)
*   Pin 2  → Pause button (INPUT_PULLUP)
*   Pin 7  → Door TTL out
*   Pin 8  → LED TTL out
*   Pin 11 → RGB Red
*   Pin 10 → RGB Green
*   Pin 12 → RGB Blue
*/
#include <AccelStepper.h>





// ─── Pins ────────────────────────────────────────────
#define STEP_PIN         4
#define DIR_PIN          5
#define EN_PIN           6
#define BUTTON_PIN       3
#define IR_SENSOR_PIN    13
#define STOP_BUTTON_PIN  2
#define DOOR_TTL_OUT_PIN 7
#define LED_TTL_OUT_PIN  8
#define RED_PIN          11
#define GREEN_PIN        10
#define BLUE_PIN         12


AccelStepper stepper(AccelStepper::DRIVER, STEP_PIN, DIR_PIN);

// ─── Motor config ────────────────────────────────────
// Default: 2800 (Neuropixels). PP-Int uses 2222.
// Set at session start via serial command S<n> (e.g. S2222)
int  STEPS_PER_REVOLUTION = 2800;
#define ROTATIONS            1
#define MAX_SPEED            3000
#define ACCELERATION         20000
#define SLOW_SPEED           (MAX_SPEED / 4)
#define NUDGE_STEPS          250


// ─── State ───────────────────────────────────────────
bool doorOpen      = false;
bool motorMoving   = false;
bool doorClosing   = false;
bool slowMode      = false;
bool emergencyStop = false;
bool systemPaused  = false;
int  systemState   = 0;
bool debugOutput   = false;
bool irEnabled     = false;
bool ledOff        = true;
bool nudging       = false;


// ─── Non-blocking serial input buffer ────────────────
char serialBuf[16];
uint8_t serialBufIdx = 0;


// ─── Non-blocking Door TTL pulse state (pin 7) ───────
int  ttlPulsesRemaining = 0;
bool ttlPinHigh         = false;
unsigned long ttlTimer  = 0;




// ─── Non-blocking LED TTL pulse state (pin 8) ────────
int  ledTtlPulsesRemaining  = 0;
bool ledTtlPinHigh          = false;
unsigned long ledTtlTimer   = 0;

const unsigned long TTL_PULSE_MS = 8;
const unsigned long TTL_GAP_MS   = 8;


// ─── Non-blocking IR sensor state ────────────────────
bool lastIRState        = false;
bool beamArmed          = false;
bool waitingToClose     = false;
unsigned long beamBrokenTime    = 0;
unsigned long waitingToCloseTime = 0;
const unsigned long IR_ARM_MS       = 175;
const unsigned long IR_CLOSE_DELAY  = 500;
const unsigned long IR_OPEN_CONFIRM = 250;
const unsigned long IR_TIMEOUT_MS   = 5000;
bool irOpenPending      = false;
unsigned long irOpenPendingTime = 0;
bool irTimeoutTriggered = false;


// ─── Button debounce ─────────────────────────────────
bool lastButtonState = HIGH;
unsigned long lastStopButtonTime = 0;








// ─── Emergency stop recovery state ──────────────────
enum EStopPhase { ESTOP_NONE, ESTOP_FLASH, ESTOP_RETURN, ESTOP_DONE };
EStopPhase estopPhase = ESTOP_NONE;
int estopFlashCount   = 0;
bool estopFlashOn     = false;
unsigned long estopTimer = 0;


// ─── RGB easter egg ──────────────────────────────────
int rgbHue = 0;
unsigned long rgbLastUpdate = 0;


// ─── Session start flash (command 3) ─────────────────
bool sessionFlashActive    = false;
int  sessionFlashCount     = 0;
bool sessionFlashOn        = false;
unsigned long sessionFlashTimer = 0;
const int SESSION_FLASH_TOTAL  = 4;
const unsigned long SESSION_FLASH_MS = 250;


// ─── Trial start flash (command 4) ──────────────────
bool trialFlashArmed       = false;
bool trialFlashActive      = false;
int  trialFlashCount       = 0;
bool trialFlashOn          = false;
unsigned long trialFlashTimer = 0;
const int TRIAL_FLASH_TOTAL    = 3;
const unsigned long TRIAL_FLASH_MS = 100;


// ─── Helper: debug print (only if enabled) ───────────
void dbg(const char* msg) {
if (debugOutput) Serial.println(msg);
}




void dbgVal(const char* msg, long val) {
if (debugOutput) {
 Serial.print(msg);
 Serial.println(val);
}
}


// ─── LED ─────────────────────────────────────────────
void setColor(int r, int g, int b) {
analogWrite(RED_PIN, r);
analogWrite(GREEN_PIN, g);
analogWrite(BLUE_PIN, b);
}


// ─── Non-blocking Door TTL: start a pulse train ──────
void startTTL(int pulses) {
ttlPulsesRemaining = pulses;
ttlPinHigh = true;
digitalWrite(DOOR_TTL_OUT_PIN, HIGH);
ttlTimer = millis();
}




// ─── Non-blocking LED TTL: start a pulse train ───────
void startLedTTL(int pulses) {
ledTtlPulsesRemaining = pulses;
ledTtlPinHigh = true;
digitalWrite(LED_TTL_OUT_PIN, HIGH);
ledTtlTimer = millis();
}




// ─── Non-blocking TTL: update both engines ───────────
void updateTTL() {
unsigned long now = millis();




// Door TTL (pin 7)
if (ttlPulsesRemaining > 0) {
 if (ttlPinHigh) {
   if (now - ttlTimer >= TTL_PULSE_MS) {
     digitalWrite(DOOR_TTL_OUT_PIN, LOW);
     ttlPinHigh = false;
     ttlPulsesRemaining--;
     ttlTimer = now;
   }
 } else {
   if (ttlPulsesRemaining > 0 && (now - ttlTimer >= TTL_GAP_MS)) {
     digitalWrite(DOOR_TTL_OUT_PIN, HIGH);
     ttlPinHigh = true;
     ttlTimer = now;
   }
 }
}




// LED TTL (pin 8)
if (ledTtlPulsesRemaining > 0) {
 if (ledTtlPinHigh) {
   if (now - ledTtlTimer >= TTL_PULSE_MS) {
     digitalWrite(LED_TTL_OUT_PIN, LOW);
     ledTtlPinHigh = false;
     ledTtlPulsesRemaining--;
     ledTtlTimer = now;
   }
 } else {
   if (ledTtlPulsesRemaining > 0 && (now - ledTtlTimer >= TTL_GAP_MS)) {
     digitalWrite(LED_TTL_OUT_PIN, HIGH);
     ledTtlPinHigh = true;
     ledTtlTimer = now;
   }
 }
}
}


// ─── Motor helpers ───────────────────────────────────
void enableMotor() {
digitalWrite(EN_PIN, LOW);
}




void disableMotor() {
digitalWrite(EN_PIN, HIGH);
}


// ─── Nudge function ──────────────────────────────────
void nudgeDoor(int direction) {
if (motorMoving || emergencyStop || systemPaused) return;
enableMotor();
stepper.setMaxSpeed(MAX_SPEED / 2);
stepper.move(direction * NUDGE_STEPS);
nudging = true;
motorMoving = true;
Serial.println(direction > 0 ? "NUDGE_FWD" : "NUDGE_BWD");
}


// ─── Door functions ──────────────────────────────────
void openDoor() {
if (!doorOpen && !motorMoving) {
 startTTL(1);
 setColor(0, 255, 0);
 enableMotor();
 stepper.setMaxSpeed(MAX_SPEED);
 long totalSteps = (long)STEPS_PER_REVOLUTION * ROTATIONS;
 stepper.move(totalSteps);
 motorMoving = true;
 doorClosing = false;
 slowMode = false;
 doorOpen = true;
 Serial.println("DOOR_OPENING");
  }
}




void closeDoor() {
if (doorOpen && !motorMoving) {
 startTTL(2);
 if (!ledOff) setColor(0, 255, 0);
 enableMotor();
 long totalSteps = (long)STEPS_PER_REVOLUTION * ROTATIONS;
 stepper.move(-totalSteps);
 motorMoving = true;
 doorClosing = true;
 doorOpen = false;
 Serial.println("DOOR_CLOSING");
  }
}




void slowCloseDoor() {
if (doorOpen && !motorMoving) {
 startTTL(2);
 setColor(0, 255, 0);
 enableMotor();
 stepper.setMaxSpeed(SLOW_SPEED);
 long totalSteps = (long)STEPS_PER_REVOLUTION * ROTATIONS;
 stepper.move(-totalSteps);
 motorMoving = true;
 doorClosing = true;
 slowMode = true;
 doorOpen = false;
 Serial.println("DOOR_CLOSING_SLOW");
  }
}








// ─── Emergency stop (non-blocking, phase-based) ──────
void startEmergencyStop() {
emergencyStop = true;

long stoppedPosition = stepper.currentPosition();
stepper.stop();
stepper.setCurrentPosition(stoppedPosition);
disableMotor();
motorMoving = false;
nudging = false;

Serial.println("ESTOP");
startTTL(3);


estopPhase = ESTOP_FLASH;
estopFlashCount = 0;
estopFlashOn = false;
estopTimer = millis();
setColor(255, 0, 0);
estopFlashOn = true;
}




void updateEmergencyStop() {
if (estopPhase == ESTOP_NONE) return;

unsigned long now = millis();

if (estopPhase == ESTOP_FLASH) {
 if (now - estopTimer >= 200) {
   estopTimer = now;
   if (estopFlashOn) {
     setColor(0, 0, 0);
     estopFlashOn = false;
   } else {
     setColor(255, 0, 0);
     estopFlashOn = true;
     estopFlashCount++;
   }
   if (estopFlashCount >= 5) {
     estopPhase = ESTOP_RETURN;
     setColor(0, 255, 0);
     stepper.setMaxSpeed(1000);
     stepper.setAcceleration(5000);
     enableMotor();
     long target = (long)STEPS_PER_REVOLUTION * ROTATIONS;
     stepper.moveTo(target);
     motorMoving = true;
     doorOpen = true;
     dbg("Returning to open");
   }
 }
}
else if (estopPhase == ESTOP_RETURN) {
 stepper.run();
 if (stepper.distanceToGo() == 0) {
   motorMoving = false;
   disableMotor();
   stepper.setMaxSpeed(MAX_SPEED);
   stepper.setAcceleration(ACCELERATION);
   setColor(255, 0, 0);
   estopPhase = ESTOP_DONE;
   emergencyStop = false;
   systemState = 2;
   Serial.println("ESTOP_RECOVERED");
 }
}
else if (estopPhase == ESTOP_DONE) {
 estopPhase = ESTOP_NONE;
}
}



// ─── Non-blocking serial read ────────────────────────
void processSerialInput() {
while (Serial.available()) {
 char c = Serial.read();

 if (c == '\n' || c == '\r') {
   if (serialBufIdx > 0) {
     serialBuf[serialBufIdx] = '\0';




     // Debug toggle
     if (serialBuf[0] == 'd' || serialBuf[0] == 'D') {
       debugOutput = !debugOutput;
       if (debugOutput) Serial.println("Debug ON");
       serialBufIdx = 0;
       return;
     }




     // S command: set steps per revolution (e.g. S2800 or S2222)
     if (serialBuf[0] == 'S' || serialBuf[0] == 's') {
       int newSteps = atoi(serialBuf + 1);
       if (newSteps > 0) {
         STEPS_PER_REVOLUTION = newSteps;
         Serial.print("STEPS_SET:");
         Serial.println(STEPS_PER_REVOLUTION);
       }
       serialBufIdx = 0;
       return;
     }




     int cmd = atoi(serialBuf);
     handleCommand(cmd);
     serialBufIdx = 0;
   }
 }
 else if (serialBufIdx < sizeof(serialBuf) - 1) {
   serialBuf[serialBufIdx++] = c;
 }
 else {
   serialBufIdx = 0;
 }
}
}








// ─── Command handler ─────────────────────────────────
void handleCommand(int cmd) {
if (cmd == 9) {
 startEmergencyStop();
 return;
}




if (emergencyStop) return;




switch (cmd) {
 case 0:
   systemState = 0;
   irEnabled = false;
   dbg("State: idle");
   break;
 case 1:
   irEnabled = false;
   systemState = 0;
   trialFlashArmed = false;
   trialFlashActive = false;
   ledOff = true;
   setColor(0, 0, 0);
   Serial.println("READY");
   break;
 case 2:
   systemState = 2;
   irEnabled = true;
   dbg("State: IR enabled");
   break;
 case 3:
   sessionFlashActive = true;
   sessionFlashCount = 0;
   sessionFlashOn = true;
   sessionFlashTimer = millis();
   ledOff = false;
   setColor(255, 0, 0);
   digitalWrite(LED_TTL_OUT_PIN, HIGH);
   Serial.println("SESSION_FLASH");
   break;
 case 4:
   trialFlashArmed = true;
   irEnabled = true;
   ledOff = false;
   Serial.println("TRIAL_ARMED");
   break;
 case 5:
   irEnabled = false;
   systemState = 0;
   trialFlashArmed = false;
   trialFlashActive = false;
   sessionFlashActive = false;
   ledOff = true;
   setColor(0, 0, 0);
   if (doorOpen && !motorMoving) {
     closeDoor();
   }
   Serial.println("SESSION_END");
   break;
 case 6:
   irEnabled = true;
   if (doorClosing && motorMoving) {
     stepper.setMaxSpeed(MAX_SPEED);
     slowMode = false;
     doorClosing = false;
     doorOpen = true;
     stepper.moveTo((long)STEPS_PER_REVOLUTION * ROTATIONS);
     startTTL(1);
     Serial.println("CLOSE_REVERSED");
   }
   else if (!doorOpen && !motorMoving) {
     if (trialFlashArmed) {
       trialFlashArmed = false;
       trialFlashActive = true;
       trialFlashCount = 0;
       trialFlashOn = true;
       trialFlashTimer = millis();
       setColor(0, 255, 0);
       digitalWrite(LED_TTL_OUT_PIN, HIGH);
       Serial.println("TRIAL_FLASH");
     } else {
       openDoor();
     }
   } else {
     dbg("Already open");
   }
   break;
 case 7:
   if (doorOpen) {
     closeDoor();
   } else {
     dbg("Already closed");
   }
   break;
 case 10:
   nudgeDoor(1);
   break;
 case 11:
   nudgeDoor(-1);
   break;
 case 22:
   systemState = 22;
   dbg("Easter egg");
   break;
 default:
   systemState = cmd;
   dbgVal("State: ", cmd);
   break;
}
}








// ─── IR sensor logic (non-blocking) ──────────────────
void updateIR() {
if (!irEnabled || emergencyStop || systemPaused || sessionFlashActive) return;




bool irDetected = digitalRead(IR_SENSOR_PIN) == LOW;




if (waitingToClose) {
 if (irDetected) {
   dbg("Close canceled");
   waitingToClose = false;
   beamArmed = false;
   beamBrokenTime = millis();
 }
 else if (millis() - waitingToCloseTime >= IR_CLOSE_DELAY) {
   dbg("IR close confirmed");
   waitingToClose = false;
   closeDoor();
   systemState = 0;
 }
 return;
}




if (irOpenPending) {
 if (!irDetected) {
   if (!trialFlashArmed) {
     dbg("IR open canceled");
     irOpenPending = false;
   }
 }
 if (irOpenPending && millis() - irOpenPendingTime >= IR_OPEN_CONFIRM) {
   irOpenPending = false;
   if (trialFlashArmed) {
     trialFlashArmed = false;
     trialFlashActive = true;
     trialFlashCount = 0;
     trialFlashOn = true;
     trialFlashTimer = millis();
     setColor(0, 255, 0);
     digitalWrite(LED_TTL_OUT_PIN, HIGH);
     Serial.println("TRIAL_FLASH");
   } else {
     dbg("IR open confirmed");
     openDoor();
   }
 }
 return;
}




if (irDetected != lastIRState) {
 lastIRState = irDetected;




 if (irDetected) {
   beamBrokenTime = millis();
   irTimeoutTriggered = false;
   Serial.println("IR:1");
 } else {
   Serial.println("IR:0");
   irTimeoutTriggered = false;
   if (beamArmed && doorOpen) {
     waitingToClose = true;
     waitingToCloseTime = millis();
   }
   beamArmed = false;
 }
}




if (irDetected && !beamArmed && !waitingToClose &&
   millis() - beamBrokenTime >= IR_ARM_MS) {
 beamArmed = true;
 dbg("IR armed");
}




if (irDetected && !doorOpen && !motorMoving && !irOpenPending && !trialFlashActive) {
 irOpenPending = true;
 irOpenPendingTime = millis();
}
}


// ─── Pause button ────────────────────────────────────
void updatePauseButton() {
unsigned long now = millis();
if (digitalRead(STOP_BUTTON_PIN) == LOW && now - lastStopButtonTime > 300) {
 systemPaused = !systemPaused;
 lastStopButtonTime = now;
 if (systemPaused) {
   dbg("Paused");
   setColor(255, 150, 0);
   stepper.stop();
   motorMoving = false;
   nudging = false;
   disableMotor();
 } else {
   dbg("Unpaused");
   setColor(255, 0, 0);
 }
}
}


// ─── Toggle button ───────────────────────────────────
void updateToggleButton() {
bool currentState = digitalRead(BUTTON_PIN);
if (lastButtonState == HIGH && currentState == LOW) {
 if (doorOpen) closeDoor();
 else openDoor();
}
lastButtonState = currentState;
}








// ─── Session start flash ─────────────────────────────
void updateSessionFlash() {
if (!sessionFlashActive) return;




if (millis() - sessionFlashTimer >= SESSION_FLASH_MS) {
 sessionFlashTimer = millis();
 if (sessionFlashOn) {
   setColor(0, 0, 0);
   digitalWrite(LED_TTL_OUT_PIN, LOW);
   sessionFlashOn = false;
 } else {
   setColor(255, 0, 0);
   digitalWrite(LED_TTL_OUT_PIN, HIGH);
   sessionFlashOn = true;
   sessionFlashCount++;
 }
 if (sessionFlashCount >= SESSION_FLASH_TOTAL) {
   sessionFlashActive = false;
   digitalWrite(LED_TTL_OUT_PIN, LOW);
   setColor(255, 0, 0);
   Serial.println("SESSION_FLASH_DONE");




   trialFlashArmed = true;
   irEnabled = true;
   Serial.println("TRIAL_ARMED");
 }
}
}








// ─── Trial start flash (green, 1s) ──────────────────
void updateTrialFlash() {
if (!trialFlashActive) return;




if (millis() - trialFlashTimer >= TRIAL_FLASH_MS) {
 trialFlashTimer = millis();
 if (trialFlashOn) {
   setColor(0, 0, 0);
   digitalWrite(LED_TTL_OUT_PIN, LOW);
   trialFlashOn = false;
 } else {
   setColor(0, 255, 0);
   digitalWrite(LED_TTL_OUT_PIN, HIGH);
   trialFlashOn = true;
   trialFlashCount++;
 }
 if (trialFlashCount >= TRIAL_FLASH_TOTAL) {
   trialFlashActive = false;
   digitalWrite(LED_TTL_OUT_PIN, LOW);
   Serial.println("TRIAL_FLASH_DONE");
   openDoor();
 }
}
}// ─── RGB easter egg ──────────────────────────────────
void updateRGB() {
if (systemState != 22) return;

if (millis() - rgbLastUpdate < 10) return;
rgbLastUpdate = millis();

float h = rgbHue / 60.0;
int i = (int)h;
float f = h - i;
float q = 1.0 - f;
float t = f;

int r, g, b;
switch (i % 6) {
 case 0: r = 255; g = t * 255; b = 0;       break;
 case 1: r = q * 255; g = 255; b = 0;       break;
 case 2: r = 0; g = 255; b = t * 255;       break;
 case 3: r = 0; g = q * 255; b = 255;       break;
 case 4: r = t * 255; g = 0; b = 255;       break;
 case 5: r = 255; g = 0; b = q * 255;       break;
}
setColor(r, g, b);

rgbHue = (rgbHue + 1) % 360;
}// =============================================================
void setup() {
Serial.begin(9600);

pinMode(STEP_PIN, OUTPUT);
pinMode(DIR_PIN, OUTPUT);
pinMode(EN_PIN, OUTPUT);
pinMode(BUTTON_PIN, INPUT_PULLUP);
pinMode(IR_SENSOR_PIN, INPUT);
pinMode(STOP_BUTTON_PIN, INPUT_PULLUP);
pinMode(RED_PIN, OUTPUT);
pinMode(GREEN_PIN, OUTPUT);
pinMode(BLUE_PIN, OUTPUT);
pinMode(DOOR_TTL_OUT_PIN, OUTPUT);
digitalWrite(DOOR_TTL_OUT_PIN, LOW);
pinMode(LED_TTL_OUT_PIN, OUTPUT);
digitalWrite(LED_TTL_OUT_PIN, LOW);

disableMotor();

stepper.setMaxSpeed(MAX_SPEED);
stepper.setAcceleration(ACCELERATION);
stepper.setCurrentPosition(0);
disableMotor();
setColor(255, 0, 0);
}// =============================================================
void loop() {
// 1. Always read serial (non-blocking, never stalls)
processSerialInput();

// 2. TTL pulse train (non-blocking)
updateTTL();

// 3. Emergency stop recovery (non-blocking)
if (emergencyStop || estopPhase != ESTOP_NONE) {
 updateEmergencyStop();
 return;
}

// 4. If paused, only check unpause button
if (systemPaused) {
 updatePauseButton();
 return;
}

// 5. Motor movement
if (motorMoving) {
 if (!nudging && doorClosing) {
   bool irNow = digitalRead(IR_SENSOR_PIN) == LOW;
   if (irNow && !slowMode) {
     long pausedPos = stepper.currentPosition();
     stepper.stop();
     stepper.setCurrentPosition(pausedPos);
     stepper.moveTo(0);
     slowMode = true;
     Serial.println("CLOSING_PAUSED");
   }
   else if (!irNow && slowMode) {
     stepper.setMaxSpeed(MAX_SPEED);
     stepper.moveTo(0);
     slowMode = false;
     Serial.println("CLOSING_RESUMED");
   }
 }

 if (!slowMode) {
   stepper.run();
 }

 if (!slowMode && stepper.distanceToGo() == 0) {
   motorMoving = false;
   if (nudging) {
     nudging = false;
     stepper.setMaxSpeed(MAX_SPEED);
     disableMotor();
     Serial.println("NUDGE_DONE");
   } else {
     bool wasDoorClosing = doorClosing;
     doorClosing = false;
     slowMode = false;
     disableMotor();
     stepper.setMaxSpeed(MAX_SPEED);
     if (wasDoorClosing) {
       irEnabled = false;
     }
     if (ledOff) {
       setColor(0, 0, 0);
     } else {
       setColor(255, 0, 0);
     }
     if (doorOpen) Serial.println("DOOR_OPEN");
     else Serial.println("DOOR_CLOSED");
   }
 }
}

// 6. Session start flash
updateSessionFlash();

// 7. Trial start flash
updateTrialFlash();

// 8. IR sensor
updateIR();

// 9. Buttons
updatePauseButton();
updateToggleButton();

// 10. Easter egg
updateRGB();
}
