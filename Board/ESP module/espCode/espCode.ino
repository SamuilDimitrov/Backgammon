#include <Arduino.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "esp_camera.h"
#include <ArduinoJson.h>
#include <WiFiManager.h>


// Set up I2C bus pins
#define I2C_SDA 0
#define I2C_SCL 16
LiquidCrystal_I2C lcd(0x27, 16, 2);

// CAMERA_MODEL_AI_THINKER
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

// set up WiFi connection and WiFi client
WiFiClient client;
HTTPClient http;

/// Server properties
String serverName = "192.168.0.110";
String uploadPath = "/uploadPhoto";
const int serverPort = 5000;

const String uniqueDeviceId = "ZA0LYxtEdD"; // Unique device Id
String gameId = "";                         // Game Id - Used to link device with a specific game
String playerOnTurn = "";
String devicePlayerColor = "";
long lastRequestTime = 0;

// move directions coming from server
struct incomingDirection
{
    uint8_t startPositionX;
    uint8_t startPositionY;
    uint8_t endPositionX;
    uint8_t endPositionY;
};

struct Dice
{
    uint8_t dice1;
    uint8_t dice2;
} dices;

// Step motor
#define DIR_PIN_X 2
#define STEP_PIN_X 14
#define STEPS_PER_REVOLUTION_X 200
#define DIR_PIN_Y 15
#define STEP_PIN_Y 13
#define STEPS_PER_REVOLUTION_Y 200
#define Y_POSITIONS 15
#define MIDDLE_ROW_POSITION 7

#define ELECTROMAGNET 12
#define MAIN_BUTTON 3

// Coordinates of key checkers possition
int keyXCoordinates[24] = {421, 393, 364, 336, 307, 279, 201, 173, 116, 144, 87, 59, 59, 87, 116, 144, 173, 201, 279, 307, 336, 364, 393, 421};
int keyYCoordinates[15] = {360, 333, 307, 280, 253, 227, 200, 173, 147, 120, 93, 67, 40};
int currX, currY;

void setup()
{
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); // Turn off BROWN_OUT detector

    //  Initialise I2C Bus and LCD display
    Wire1.begin(I2C_SDA, I2C_SCL, 100000);

    lcd.init();      // init display
    lcd.clear();     // clear display
    lcd.backlight(); // turn display backlight ON
    writeToDisplay("Connecting to", "WiFi...");
    delay(500);
    //  Connect to WiFi
    WiFi.mode(WIFI_STA);
    
    WiFiManager wm;
    bool res;
    res = wm.autoConnect("Backgammon_Board"); //configure AP with ssid
    if(!res) {
        Serial.println("Failed to connect");
        ESP.restart();
    } 
    
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
    }
    writeToDisplay("Conencted to", "WiFi");
    delay(1000);
    lcd.clear(); // clear display

    //  Initialise camera
    configureCamera();

    delay(1000);

    //  Initialise step motors and electromagnet
    pinMode(DIR_PIN_X, OUTPUT);
    pinMode(STEP_PIN_X, OUTPUT);
    pinMode(DIR_PIN_Y, OUTPUT);
    pinMode(STEP_PIN_Y, OUTPUT);
    pinMode(ELECTROMAGNET, OUTPUT);
    pinMode(MAIN_BUTTON, INPUT_PULLUP);

    writeToDisplay("Waiting for game", "");
}

void loop()
{

    if (playerOnTurn != "")
    {
        if (playerOnTurn == devicePlayerColor)
        {
            writeToDisplay("Press button", "to row dice");
            bool pressed = false;
            while (1)
            {
                if (!pressed && digitalRead(MAIN_BUTTON))
                {
                    pressed = true;
                }
                else if (pressed && !digitalRead(MAIN_BUTTON))
                {
                    pressed = false;
                    break;
                }
            }
            RowDice();
            String dice_str = "";
            dice_str += dices.dice1;
            dice_str += " and ";
            dice_str += dices.dice2;
            writeToDisplay("   You rowed:", dice_str);

            while (1)
            {
                if (!pressed && digitalRead(MAIN_BUTTON))
                {
                    pressed = true;
                }
                else if (pressed && !digitalRead(MAIN_BUTTON))
                {
                    pressed = false;
                    break;
                }
            }
            int sendResult = 0;

            do
            {
                sendResult = sendPhoto();
                if (sendResult == 1)
                {
                    writeToDisplay("Check for camera", "obstructions");
                }
                else if (sendResult == 2)
                {
                    writeToDisplay("Illegal move.", "Correct your move");
                }
                else if (sendResult == 3)
                {
                    writeToDisplay("Game not", "detected.");
                }
                delay(500);
                sendResult = 0;
            } while (sendResult != 0);
        }
        else
        {
            if (millis() - lastRequestTime >= 3000)
            {
                getGameData();
                if (dices.dice1 == 0 && dices.dice2 == 0)
                {
                    writeToDisplay("Waiting for", "oponent to row");
                }
                else if (dices.dice1 != 0 && dices.dice2 != 0)
                {
                    String dice_str = "";
                    dice_str += dices.dice1;
                    dice_str += " and ";
                    dice_str += dices.dice2;
                    writeToDisplay("Oponent rowed:", dice_str);
                }
            }
        }
    }
    if (millis() - lastRequestTime >= 3000)
    {
        updateDeviceStatus();
        lastRequestTime = millis();
    }
}

// Reset device to not playing
void resetGame()
{
    dices.dice1 = 0;
    dices.dice2 = 0;
    gameId = "";
    playerOnTurn = "";
    devicePlayerColor = "";

    int distanceToMove = currY;
    digitalWrite(DIR_PIN_Y, false);
    int stepsToMove = (abs(distanceToMove) * 200) / 80;
    for (int i = 0; i < stepsToMove; i++)
    {
        digitalWrite(STEP_PIN_Y, HIGH);
        delayMicroseconds(2000);
        digitalWrite(STEP_PIN_Y, LOW);
        delayMicroseconds(2000);
    }
    currY = 0;
    delay(500);

    distanceToMove = currX;
    digitalWrite(DIR_PIN_X, false);
    stepsToMove = (abs(distanceToMove) * 200) / 80;
    for (int i = 0; i < stepsToMove; i++)
    {
        digitalWrite(STEP_PIN_X, HIGH);
        delayMicroseconds(2000);
        digitalWrite(STEP_PIN_X, LOW);
        delayMicroseconds(2000);
    }
    currX = 0;
    delay(500);
    writeToDisplay("Waiting for game", "");
}

// write To Display
uint8_t writeToDisplay(String line1, String line2)
{
    lcd.clear();
    lcd.setCursor(0, 0); // Set cursor to character 0 on line 0
    lcd.print(line1);

    lcd.setCursor(0, 1); // Move cursor to character 0 on line 1
    lcd.print(line2);
}

int RowDice()
{
    if ((WiFi.status() == WL_CONNECTED))
    {
        if (gameId != "")
        {
            http.begin(serverName, serverPort, "/ajaxDiceRow/" + gameId);
            int httpCode = http.GET();
            if (httpCode > 0)
            {
                String payload = http.getString();
                decodeJsonDirection(payload);
            }
            else
            {
                Serial.print("Error on HTTP request with code: ");
                Serial.println(httpCode);
            }
            http.end();
            return httpCode;
        }
    }
}

// Send get request to the server to notify him that the device is online
// and to check if a game has started
int updateDeviceStatus()
{
    if ((WiFi.status() == WL_CONNECTED))
    {
        http.begin(serverName, serverPort, "/deviceUpdate?deviceId=" + uniqueDeviceId);
        int httpCode = http.GET();
        if (httpCode > 0)
        {
            String payload = http.getString();
            if (payload != "{}\n" && gameId == "")
            {
                const size_t capacity = JSON_OBJECT_SIZE(1) + 50;
                DynamicJsonDocument doc(capacity);
                DeserializationError error = deserializeJson(doc, payload);
                if (error)
                {
                    return 1;
                }

                String id = doc["gameId"];
                gameId = id;

                startGameRequest();
            }
            else if (payload == "{}\n" && gameId != "")
            {
                resetGame();
            }
        }
        http.end();
        return httpCode;
    }
}

//comformation that the device is OK when starting a game
int startGameRequest()
{
    if ((WiFi.status() == WL_CONNECTED))
    {
        http.begin(serverName, serverPort, "/confirmGameStart?deviceId=" + uniqueDeviceId + "&gameId=" + gameId);
        int httpCode = http.GET();
        if (httpCode > 0)
        {
            String payload = http.getString();
            decodeJsonDirection(payload);
        }
        http.end();
        return httpCode;
    }
}

//request game data(move directions, opponent dice row...)
int getGameData()
{
    if ((WiFi.status() == WL_CONNECTED))
    {
        http.begin(serverName, serverPort, "/getGameData?deviceId=" + uniqueDeviceId + "&gameId=" + gameId);
        int httpCode = http.GET();
        if (httpCode > 0)
        {
            String payload = http.getString();
            decodeJsonDirection(payload);
        }
        http.end();
        return httpCode;
    }
}

void decodeJsonDirection(String rawJson)
{
    int count = 0;
    for (int i = 0; rawJson[i]; i++)
    {
        count += (rawJson[i] == '{');
    }
    const size_t capacity = JSON_OBJECT_SIZE(1) + 20 + JSON_ARRAY_SIZE(count) + JSON_OBJECT_SIZE(3) + count * JSON_OBJECT_SIZE(2) + 20 + 20 * count;
    DynamicJsonDocument doc(capacity);
    DeserializationError error = deserializeJson(doc, rawJson);

    if (error)
    {
        return;
    }

    String diceData = doc["dice"];
    if (diceData != "null")
    {
        dices.dice1 = doc["dice"][0];
        dices.dice2 = doc["dice"][1];
    }

    String id = doc["gameId"];
    String deserialisedPlayerOnTurn = doc["playerOnTurn"];
    String deserialisedDevicePlayerColor = doc["playerColor"];
    if (deserialisedPlayerOnTurn != "null")
    {
        playerOnTurn = deserialisedPlayerOnTurn;
    }
    if (deserialisedDevicePlayerColor != "null")
    {
        devicePlayerColor = deserialisedDevicePlayerColor;
    }

    for (int i = 0; i < doc["move"].size(); i++)
    {
        incomingDirection dir;
        String start = doc["move"][i]["From"];
        int temp = start.indexOf('_');
        dir.startPositionX = start.substring(0, temp).toInt();
        dir.startPositionY = start.substring(temp + 1).toInt();

        String destination = doc["move"][i]["To"];
        temp = destination.indexOf('_');
        dir.endPositionX = destination.substring(0, temp).toInt();
        dir.endPositionY = destination.substring(temp + 1).toInt();
        makePath(dir);
    }
}

void configureCamera()
{
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM;
    config.pin_sscb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;

    if (psramFound())
    {
        config.frame_size = FRAMESIZE_UXGA;
        config.jpeg_quality = 10;
        config.fb_count = 2;
    }
    else
    {
        config.frame_size = FRAMESIZE_SVGA;
        config.jpeg_quality = 12;
        config.fb_count = 1;
    }
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK)
    {
        delay(1000);
        ESP.restart();
    }
}

int sendPhoto()
{
    String getAll;
    String getBody;

    camera_fb_t *fb = NULL;
    fb = esp_camera_fb_get();
    if (!fb)
    {
        delay(1000);
        return -1;
    }

    if (client.connect(serverName.c_str(), serverPort))
    {
        String head = "--SendPhoto\r\nContent-Disposition: form-data; name=\"imageFile\"; filename=\"esp32-cam.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";
        String tail = "\r\n--SendPhoto--\r\n";

        uint32_t imageLen = fb->len;
        uint32_t extraLen = head.length() + tail.length();
        uint32_t totalLen = imageLen + extraLen;
        String myPOST = "POST " + uploadPath + "?deviceId=" + uniqueDeviceId + " HTTP/1.1\r\n" + "Host: " + serverName + "\r\n" + "Content-Length: " + String(totalLen) + "\r\n" + "Content-Type: multipart/form-data; boundary=SendPhoto" + "\r\n\r\n";
        client.print(myPOST);
        client.flush();
        client.print(head);
        client.flush();

        uint8_t *fbBuf = fb->buf;
        size_t fbLen = fb->len;
        for (size_t n = 0; n < fbLen; n = n + 1024)
        {
            if (n + 1024 < fbLen)
            {
                client.write(fbBuf, 1024);
                fbBuf += 1024;
            }
            else if (fbLen % 1024 > 0)
            {
                size_t remainder = fbLen % 1024;
                client.write(fbBuf, remainder);
            }
        }
        client.print(tail);
        client.flush();
        esp_camera_fb_return(fb);

        int timoutTimer = 10000;
        long startTimer = millis();
        boolean state = false;

        while ((startTimer + timoutTimer) > millis())
        {
            delay(100);
            while (client.available())
            {
                char c = client.read();
                if (c == '\n')
                {
                    if (getAll.length() == 0)
                    {
                        state = true;
                    }
                    getAll = "";
                }
                else if (c != '\r')
                {
                    getAll += String(c);
                }
                if (state == true)
                {
                    getBody += String(c);
                }
                startTimer = millis();
            }
            if (getBody.length() > 0)
            {
                break;
            }
        }
        client.stop();
        if (getBody.length() == 0)
        {
            return 2;
        }
    }
    else
    {
        return 1;
    }
    if (getBody == "OK")
    {
        return 0;
    }
    else if (getBody == "BAD_IMG")
    {
        return 1;
    }
    else if (getBody == "ILLEGAL_MOVE")
    {
        return 2;
    }
    else if (getBody == "NO_GAME_FOUND")
    {
        return 3;
    }
}

void makePath(incomingDirection ckeckerMove)
{
    turnXmotor(ckeckerMove.startPositionX);
    delay(100);
    if (ckeckerMove.startPositionX <= 11)
    {
        turnYmotor(ckeckerMove.startPositionY);
    }
    else
    {
        turnYmotor(Y_POSITIONS - ckeckerMove.startPositionY);
    }
    delay(100);
    digitalWrite(ELECTROMAGNET, true);
    delay(100);
    turnYmotor(MIDDLE_ROW_POSITION);
    delay(100);
    turnXmotor(ckeckerMove.endPositionX);
    delay(100);
    if (ckeckerMove.startPositionX <= 11)
    {
        turnYmotor(ckeckerMove.endPositionY);
    }
    else
    {
        turnYmotor(Y_POSITIONS - ckeckerMove.endPositionY);
    }
    delay(100);
    digitalWrite(ELECTROMAGNET, false);
}

void turnXmotor(int destinationX)
{
    int distanceToMove = currX - keyXCoordinates[destinationX];
    if (distanceToMove < 0)
    {
        digitalWrite(DIR_PIN_X, true);
    }
    else
    {
        digitalWrite(DIR_PIN_X, false);
    }
    int stepsToMove = (abs(distanceToMove) * 200) / 80;

    for (int i = 0; i < stepsToMove; i++)
    {
        digitalWrite(STEP_PIN_X, HIGH);
        delayMicroseconds(2000);
        digitalWrite(STEP_PIN_X, LOW);
        delayMicroseconds(2000);
    }
    currX = keyXCoordinates[destinationX];
}

void turnYmotor(int destinationY)
{
    destinationY--;
    int distanceToMove = currY - keyYCoordinates[destinationY];
    if (distanceToMove < 0)
    {
        digitalWrite(DIR_PIN_Y, true);
    }
    else
    {
        digitalWrite(DIR_PIN_Y, false);
    }
    int stepsToMove = (abs(distanceToMove) * 200) / 80;

    for (int i = 0; i < stepsToMove; i++)
    {
        digitalWrite(STEP_PIN_Y, HIGH);
        delayMicroseconds(2000);
        digitalWrite(STEP_PIN_Y, LOW);
        delayMicroseconds(2000);
    }
    currY = keyYCoordinates[destinationY];
    delay(500);
}
