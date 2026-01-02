#include <WiFi.h>
#include <HTTPClient.h> // Switch to Standard HTTP Client
#include <Wire.h>
#include <LiquidCrystal_I2C.h> // Library: "LiquidCrystal I2C" by Frank de Brabander

// ===== PINS & CONFIG =====
#define PIN_START   32
#define PIN_ERROR   33
#define PIN_FINISH  25
#define PIN_LED     2
#define BUZZER      13

const char* WIFI_SSID = "Phong Tin Nha A";
const char* WIFI_PASS = "phongtin2";
const char* SERVER_IP = "192.168.1.9"; // Update IP if needed
const int SERVER_PORT = 5000;

LiquidCrystal_I2C lcd(0x27, 16, 2); // Address 0x27 usually, sometimes 0x3F

// Game State
bool gameStarted = false;
bool finished = false;
unsigned long startTime = 0;
int errorCount = 0;
unsigned long lastUpdate = 0;

// Buzzer State
int buzChannel = 0;
unsigned long buzzerUntil = 0;
bool isBuzzing = false;

// ===== BUZZER (NON-BLOCKING) =====
void startBuzzer(int frequency, int duration) {
    ledcWriteTone(buzChannel, frequency);
    ledcWrite(buzChannel, 255);
    buzzerUntil = millis() + duration;
    isBuzzing = true;
}

void updateBuzzer() {
    if (isBuzzing && millis() > buzzerUntil) {
        ledcWriteTone(buzChannel, 0);
        isBuzzing = false;
    }
}

// ===== LCD HELPERS =====
void updateLCD(String line1, String line2) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(line1);
    lcd.setCursor(0, 1);
    lcd.print(line2);
}

void updateLCDGame(float time, int errors) {
    lcd.setCursor(0, 0);
    lcd.print("Time: " + String(time, 1) + "s   ");
    lcd.setCursor(0, 1);
    lcd.print("Err: " + String(errors) + "      ");
}

// ===== HTTP SENDER (ROBUST) =====
void sendEvent(String eventType, float timePlay, int errors) {
    if(WiFi.status() == WL_CONNECTED){
        HTTPClient http;
        String url = "http://" + String(SERVER_IP) + ":" + String(SERVER_PORT) + "/api/game_event";
        
        http.begin(url);
        http.addHeader("Content-Type", "application/json");
        
        String json = "{\"event\":\"" + eventType + "\",\"time\":" + String(timePlay, 2) + ",\"errors\":" + String(errors) + "}";
        
        // POST asynchronously essentially (we don't wait long for response or check strict validity to keep game smooth)
        // For 'update' events, we might want to skip waiting, but for start/finish we wait.
        int httpResponseCode = http.POST(json);
        
        if (httpResponseCode > 0) {
           Serial.print("HTTP Sent: "); Serial.println(eventType);
        } else {
           Serial.print("Error on sending POST: "); Serial.println(httpResponseCode);
        }
        http.end();
    } else {
        Serial.println("WiFi Disconnected");
    }
}

void setup() {
    Serial.begin(115200);

    // Initialise LCD
    Wire.begin(22, 23); // SDA=21, SCL=22
    lcd.init();
    lcd.backlight();
    updateLCD("System Init...", "Pls Wait");

    // Pins
    pinMode(PIN_START, INPUT_PULLUP);
    pinMode(PIN_ERROR, INPUT_PULLUP);
    pinMode(PIN_FINISH, INPUT_PULLUP);
    pinMode(PIN_LED, OUTPUT);

    // Buzzer Setup
    ledcSetup(buzChannel, 2000, 8);
    ledcAttachPin(BUZZER, buzChannel);

    // WiFi
    updateLCD("WiFi Connecting", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi Connected!");
    updateLCD("Connected!", "Touch Start Pt");
    
    startBuzzer(1000, 200);
    delay(200);
    startBuzzer(2000, 200);
}

void resetGame() {
    gameStarted = false;
    finished = false;
    errorCount = 0;
    digitalWrite(PIN_LED, LOW);
    startBuzzer(2000, 300); // Reset sound
    updateLCD("Reset Game", "Touch A to Start");
}

void loop() {
    updateBuzzer();

    int startState = digitalRead(PIN_START);
    int errorState = digitalRead(PIN_ERROR);
    int finishState = digitalRead(PIN_FINISH);

    // 1. Reset (Chạm A)
    if (startState == LOW) {
        if (gameStarted || finished) {
            resetGame();
            delay(500); // Debounce
        }
        return;
    }

    // 2. Start (Rời A)
    if (!gameStarted && !finished && startState == HIGH) {
        gameStarted = true;
        startTime = millis();
        lastUpdate = millis();
        startBuzzer(2000, 300);
        sendEvent("start", 0, 0);
        lcd.clear();
    }

    // 3. Playing
    if (gameStarted && !finished) {
        float currentTime = (millis() - startTime) / 1000.0;

        // Error (Chạm B)
        if (errorState == LOW) {
            digitalWrite(PIN_LED, HIGH);
            if (!isBuzzing) startBuzzer(3000, 80); // Short beep
            
            static unsigned long lastErrorTime = 0;
            if (millis() - lastErrorTime > 200) {
                 errorCount++;
                 sendEvent("update", currentTime, errorCount);
                 lastErrorTime = millis();
            }
            digitalWrite(PIN_LED, LOW);
        }

        // Periodic Update (LCD + Server)
        // Reduce network spam: Only send every 200ms
        if (millis() - lastUpdate > 200) { 
            sendEvent("update", currentTime, errorCount);
            updateLCDGame(currentTime, errorCount);
            lastUpdate = millis();
        }

        // Finish (Chạm C)
        if (finishState == LOW) {
            finished = true;
            startBuzzer(2000, 500); // Long beep
            sendEvent("finish", currentTime, errorCount);
            
            lcd.clear();
            lcd.setCursor(0, 0);
            lcd.print("DONE! T: " + String(currentTime, 1) + "s");
            lcd.setCursor(0, 1);
            lcd.print("Errors: " + String(errorCount));
        }
    }
}
