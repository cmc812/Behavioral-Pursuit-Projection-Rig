/*
 * camera_trigger_and_sync.ino
 *
 * Three functions on one Arduino Uno:
 *   1. 30 Hz hardware-timed camera trigger (Timer1 CTC, pin 9)
 *   2. Sync IR LED + TTL (pin 5 + pin 8) — pseudorandom 3-16 frame interval
 *   3. Non-IR LED (pin 6) — flashes simultaneously with IR LED
 *
 * On START:
 *   1. 5s of steady 5 Hz pulses: both LEDs + TTL HIGH
 *   2. LEDs off, 30 Hz triggering + synced LED flashes begin
 *   3. SESSION sent 12s after START to signal Bonsai
 *
 * Each LED flash is 5ms, synced with the frame trigger edge.
 * Both LEDs flash together on the same random interval.
 * Only the IR LED drives the TTL line.
 *
 * Serial commands (from Bonsai, 500000 baud):
 *   START  — begin 5s pulse → triggering + both LEDs pseudorandom
 *   STOP   — immediately halt everything, all pins LOW
 *
 * Serial output:
 *   STARTED          — session begun
 *   PULSE_ON         — 5s startup pulse began
 *   PULSE_OFF        — 5s startup pulse ended, triggering begins
 *   micros,event     — CSV header
 *   SESSION          — sent 12s after START (DLC init complete)
 *   SYNC_ON          — both LEDs flashed (IR + TTL)
 *   F:N              — frame N triggered
 *   STOPPED frames=N — session ended
 *
 * Wiring:
 *   Pin 9  → 1kΩ → GH3 Pin 1 (opto input, camera trigger)
 *   Pin 5  → IR LED (sync)
 *   Pin 6  → Non-IR LED (sync, no TTL)
 *   Pin 8  → Open Ephys I/O board (sync TTL, IR only)
 *   GND    → GH3 Pin 6 (OPTO_GND) + LED grounds + OE I/O GND
 *   GH3 opto output → Open Ephys I/O board (ExposureActive TTL)
 */

// ─── Pin assignments ─────────────────────────────────
const int TRIGGER_PIN  = 9;   // PORTB bit 1
const int IR_LED_PIN   = 5;   // PORTD bit 5
const int VIS_LED_PIN  = 6;   // PORTD bit 6
const int TTL_OUT_PIN  = 8;   // PORTB bit 0

// ─── Camera trigger config ───────────────────────────
const int   PULSE_US   = 50;
const float FRAME_RATE = 30.0;

const unsigned long PERIOD_US  = (unsigned long)(1000000.0 / FRAME_RATE);
const unsigned int  TIMER1_TOP = (PERIOD_US * 2) - 1;

volatile unsigned long frameCount = 0;

// ─── LED flash turn-off (set in ISR, cleared in loop) ──
const unsigned long FLASH_MS = 5;
volatile bool       syncFlashActive = false;
volatile unsigned long syncFlashStart = 0;

// ─── Random interval config (shared for both LEDs) ──
const int SYNC_MIN_INTERVAL = 3;
const int SYNC_MAX_INTERVAL = 16;

volatile int syncNextFlashFrame = 0;

// ─── Session state ───────────────────────────────────
bool running = false;
unsigned long sessionStartUs = 0;
bool sessionSent = false;
unsigned long sessionSendTime = 0;
const unsigned long SESSION_DELAY_MS = 12000;

// ─── Startup pulse state ─────────────────────────────
bool startupPulseActive = false;
unsigned long startupPulseEnd = 0;
const unsigned long STARTUP_PULSE_MS = 5000;
const unsigned long STARTUP_BLINK_MS = 100;  // 5 Hz = 100ms on, 100ms off
unsigned long startupBlinkTimer = 0;
bool startupBlinkOn = false;

// ─── Event log ring buffer ───────────────────────────
struct LogEvent {
  unsigned long timestamp_us;
  char tag[16];
};

const int LOG_BUF_SIZE = 64;
LogEvent  logBuf[LOG_BUF_SIZE];
volatile uint8_t logHead = 0;
volatile uint8_t logTail = 0;

void logEvent(unsigned long us, const char* tag) {
  uint8_t next = (logHead + 1) & (LOG_BUF_SIZE - 1);
  if (next == logTail) return;
  logBuf[logHead].timestamp_us = us - sessionStartUs;
  strncpy(logBuf[logHead].tag, tag, 15);
  logBuf[logHead].tag[15] = '\0';
  logHead = next;
}

void flushLog() {
  while (logTail != logHead) {
    Serial.print(logBuf[logTail].timestamp_us);
    Serial.print(',');
    Serial.println(logBuf[logTail].tag);
    logTail = (logTail + 1) & (LOG_BUF_SIZE - 1);
  }
}

// =============================================================
void setup() {
  pinMode(TRIGGER_PIN,  OUTPUT);
  pinMode(IR_LED_PIN,   OUTPUT);
  pinMode(VIS_LED_PIN,  OUTPUT);
  pinMode(TTL_OUT_PIN,  OUTPUT);

  digitalWrite(TRIGGER_PIN,  LOW);
  digitalWrite(IR_LED_PIN,   LOW);
  digitalWrite(VIS_LED_PIN,  LOW);
  digitalWrite(TTL_OUT_PIN,  LOW);

  Serial.begin(500000);
  randomSeed(analogRead(A0));
  configureTimer1();
}

// =============================================================
void loop() {
  // ── Serial commands ──
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.equalsIgnoreCase("START")) {
      startAll();
    } else if (cmd.equalsIgnoreCase("STOP")) {
      stopAll();
    }
  }

  // ── Startup pulse: turn off after 5s, begin random flashes ──
  if (startupPulseActive) {
    unsigned long now = millis();
    if (now >= startupPulseEnd) {
        // 5s elapsed — end startup, go to random flashes
        startupPulseActive = false;
        digitalWrite(IR_LED_PIN,  LOW);
        digitalWrite(VIS_LED_PIN, LOW);
        digitalWrite(TTL_OUT_PIN, LOW);
        Serial.println("PULSE_OFF");
        syncNextFlashFrame = frameCount + random(SYNC_MIN_INTERVAL, SYNC_MAX_INTERVAL + 1);
    } else if (now - startupBlinkTimer >= STARTUP_BLINK_MS) {
        // Toggle all three at 5 Hz
        startupBlinkTimer = now;
        startupBlinkOn = !startupBlinkOn;
        digitalWrite(IR_LED_PIN,  startupBlinkOn ? HIGH : LOW);
        digitalWrite(VIS_LED_PIN, startupBlinkOn ? HIGH : LOW);
        digitalWrite(TTL_OUT_PIN, startupBlinkOn ? HIGH : LOW);
    }
}

  // ── Turn off both LEDs + TTL after 5ms flash ──
  if (syncFlashActive && (millis() - syncFlashStart >= FLASH_MS)) {
    PORTD &= ~(1 << PD5);  // IR LED LOW
    PORTD &= ~(1 << PD6);  // VIS LED LOW
    PORTB &= ~(1 << PB0);  // TTL LOW
    syncFlashActive = false;
  }

  // ── Send SESSION after 12s ──
  if (running && !sessionSent && millis() >= sessionSendTime) {
    sessionSent = true;
    Serial.println("SESSION");
  }

  // ── Flush buffered events to serial ──
  flushLog();
}

// =============================================================
void configureTimer1() {
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = 0;
  TCNT1  = 0;

  TCCR1B |= (1 << WGM12);

  if (PERIOD_US > 32767) {
    OCR1A = (PERIOD_US / 4) - 1;
    TCCR1B |= (1 << CS11) | (1 << CS10);
  } else {
    OCR1A = TIMER1_TOP;
    TCCR1B |= (1 << CS11);
  }

  interrupts();
}

// =============================================================
void startAll() {
  if (running) return;
  running = true;

  sessionStartUs = micros();
  sessionSent = false;
  sessionSendTime = millis() + SESSION_DELAY_MS;

  Serial.println("STARTED");
  Serial.println("micros,event");

  // Start 5s steady pulse: both LEDs + TTL HIGH
  startupPulseActive = true;
  startupPulseEnd = millis() + STARTUP_PULSE_MS;
  startupBlinkTimer = millis();
  startupBlinkOn = false;
  Serial.println("PULSE_ON");

  // Start camera triggering immediately (LEDs held steady during pulse)
  frameCount = 0;
  syncNextFlashFrame = 0;  // will be set properly when pulse ends
  syncFlashActive = false;

  TCNT1 = 0;
  TIMSK1 |= (1 << OCIE1A);
}

// =============================================================
void stopAll() {
  TIMSK1 &= ~(1 << OCIE1A);

  digitalWrite(TRIGGER_PIN,  LOW);
  digitalWrite(IR_LED_PIN,   LOW);
  digitalWrite(VIS_LED_PIN,  LOW);
  digitalWrite(TTL_OUT_PIN,  LOW);

  syncFlashActive = false;
  startupPulseActive = false;
  running = false;

  Serial.print("STOPPED frames=");
  Serial.println(frameCount);
}

// =============================================================
// Timer1 ISR — camera trigger + synced LED flashes
//   Pin 9 = PORTB bit 1    Pin 8 = PORTB bit 0
//   Pin 6 = PORTD bit 6    Pin 5 = PORTD bit 5
// =============================================================
ISR(TIMER1_COMPA_vect) {
  // Camera trigger always fires
  PORTB |= (1 << PB1);   // Pin 9 HIGH

  frameCount++;
  unsigned long now_us = micros();

  // Both LEDs + TTL flash together on the same interval
  // (skip during startup pulse — LEDs already held HIGH)
  if (!startupPulseActive && (int)frameCount >= syncNextFlashFrame) {
    PORTD |= (1 << PD5);   // IR LED HIGH
    PORTD |= (1 << PD6);   // VIS LED HIGH
    PORTB |= (1 << PB0);   // TTL HIGH
    syncFlashStart = millis();
    syncFlashActive = true;
    syncNextFlashFrame = frameCount + random(SYNC_MIN_INTERVAL, SYNC_MAX_INTERVAL + 1);
    logEvent(now_us, "SYNC_ON");
  }

  // Log frame
  char ftag[16] = "F:";
  ultoa(frameCount, ftag + 2, 10);
  logEvent(now_us, ftag);

  delayMicroseconds(PULSE_US);

  // Camera trigger LOW
  PORTB &= ~(1 << PB1);  // Pin 9 LOW
}