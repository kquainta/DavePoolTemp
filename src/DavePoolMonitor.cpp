#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>
#include "secrets.h"

// --- Configuration ---
// Credentials are in secrets.h
const char* DEVICE_ID = "pool-monitor-01";

// --- Hardware ---
const int ONE_WIRE_BUS = 4; // GPIO 4 (D2 on Wemos D1 Mini ESP32)
const int LED_PIN = 2;      // Built-in LED

// --- Objects ---
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  
  // Start sensors
  sensors.begin();
  
  // Connect to Wi-Fi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    digitalWrite(LED_PIN, !digitalRead(LED_PIN)); // Blink LED
  }
  Serial.println();
  Serial.print("Connected! IP address: ");
  Serial.println(WiFi.localIP());
  digitalWrite(LED_PIN, HIGH); // LED off (usually active low) or on depending on board
}

void loop() {
  // Request temperature
  sensors.requestTemperatures(); 
  float tempC = sensors.getTempCByIndex(0);
  float tempF = sensors.getTempFByIndex(0);

  // Check for errors
  if (tempC == DEVICE_DISCONNECTED_C) {
    Serial.println("Error: Could not read temperature data");
    delay(2000);
    return;
  }

  Serial.printf("Temperature: %.2f C / %.2f F\n", tempC, tempF);

  // Prepare JSON payload
  StaticJsonDocument<200> doc;
  doc["api_key"] = API_KEY;
  doc["device_id"] = DEVICE_ID;
  doc["temperature_c"] = tempC;
  doc["temperature_f"] = tempF;

  String jsonString;
  serializeJson(doc, jsonString);

  // Send to GCP
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(GCP_FUNCTION_URL);
    http.addHeader("Content-Type", "application/json");
    
    int httpResponseCode = http.POST(jsonString);
    
    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.printf("HTTP Response code: %d\n", httpResponseCode);
      Serial.println(response);
    } else {
      Serial.printf("Error on sending POST: %s\n", http.errorToString(httpResponseCode).c_str());
    }
    http.end();
  } else {
    Serial.println("Error: WiFi Disconnected");
  }

  // Wait before next reading (e.g., 1 minute)
  delay(60000);
}