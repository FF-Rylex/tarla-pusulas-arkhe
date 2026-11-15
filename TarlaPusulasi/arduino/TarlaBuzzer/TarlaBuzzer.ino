// Passive buzzer on D9. Non-blocking protocol: F<hz>,<seconds>,<repeat>\n
// F0,0,0 stops immediately. No delay() calls block incoming Stop commands.
const byte BUZZER_PIN = 9;
char line[64];
byte used = 0;
bool active = false;
bool pausePhase = false;
unsigned int frequency = 0;
unsigned long durationMs = 0, phaseStart = 0;
int remaining = 0;

void stopBuzzer() {
  noTone(BUZZER_PIN);
  digitalWrite(BUZZER_PIN, LOW);
  active = false;
  pausePhase = false;
  remaining = 0;
}
void command(char *text) {
  long hz = 0, seconds = 0, repeats = 0;
  if (text[0] == 'S' || text[0] == 's') {   // "S" / "STOP" da durdurur
    stopBuzzer();
    Serial.println("STOPPED");
    return;
  }
  if (sscanf(text, "F%ld,%ld,%ld", &hz, &seconds, &repeats) != 3) return;
  stopBuzzer();
  if (hz <= 0 || seconds <= 0 || repeats <= 0) {
    Serial.println("STOPPED");
    return;
  }
  frequency = (unsigned int)constrain(hz, 1L, 25000L);
  durationMs = (unsigned long)constrain(seconds, 1L, 3600L) * 1000UL;
  remaining = (int)constrain(repeats, 1L, 20L);
  phaseStart = millis();
  active = true;
  tone(BUZZER_PIN, frequency);
  Serial.println("STARTED");
}
void setup() {
  pinMode(BUZZER_PIN, OUTPUT);
  stopBuzzer();
  Serial.begin(9600);
}
void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      line[used] = 0;
      command(line);
      used = 0;
    } else if (c != '\r') {
      if (used < sizeof(line) - 1) line[used++] = c;
      else used = 0;
    }
  }
  if (!active) return;
  unsigned long elapsed = millis() - phaseStart;
  if (!pausePhase && elapsed >= durationMs) {
    noTone(BUZZER_PIN);
    remaining--;
    if (!remaining) { stopBuzzer(); return; }
    pausePhase = true;
    phaseStart = millis();
  } else if (pausePhase && elapsed >= 1000UL) {
    pausePhase = false;
    phaseStart = millis();
    tone(BUZZER_PIN, frequency);
  }
}
