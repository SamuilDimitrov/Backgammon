#include <Arduino.h>
#include <WiFi.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "esp_camera.h"

const char *ssid = "Mecho";
const char *password = "st14kr16sm20ts10";

String serverName = "192.168.0.110";
String serverPath = "/";
const int serverPort = 5000;

WiFiClient client;

char command;

// CAMERA_MODEL_AI_THINKER
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); 
  Serial.begin(115200);
  
  pinMode(33, OUTPUT);
  digitalWrite(33, LOW);
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
  digitalWrite(33, HIGH);
  //Serial.println("Wifi connected");
  delay(1000);
  digitalWrite(33, LOW);
  configureCamera();
  digitalWrite(33, HIGH);
  delay(1000);
  led();
}

void loop() {
  if(Serial.available() > 0){
    command = Serial.read(); 
  }
  if(command == '0'){
    command = 'q';
    led();
    int a = sendPhoto();
    if(!a){
      led3();
    }else if(a == 1){
      led();
    }else if(a == 2){
      ledErr();
    }
  }
}

void led(){
  digitalWrite(33, LOW);
  delay(200);
  digitalWrite(33, HIGH);
  delay(200);
  digitalWrite(33, LOW);
  delay(200);
  digitalWrite(33, HIGH);
}

void led3(){
  digitalWrite(33, LOW);
  delay(200);
  digitalWrite(33, HIGH);
  delay(200);
  digitalWrite(33, LOW);
  delay(200);
  digitalWrite(33, HIGH);
  delay(200);
  digitalWrite(33, LOW);
  delay(200);
  digitalWrite(33, HIGH);
}

void ledErr(){
  digitalWrite(33, LOW);
  delay(500);
  digitalWrite(33, HIGH);
  delay(500);
  digitalWrite(33, LOW);
  delay(500);
  digitalWrite(33, HIGH);
}

void configureCamera(){
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

  if(psramFound()){
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_CIF;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }
  
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    //Serial.println("Camera err");
    delay(1000);
    ESP.restart();
  }
}

int sendPhoto() {
  String getAll;
  String getBody;

  camera_fb_t * fb = NULL;
  fb = esp_camera_fb_get();
  if(!fb) {
    delay(1000);
    ESP.restart();
  }
  
  if (client.connect(serverName.c_str(), serverPort)) {
    String head = "--SendPhoto\r\nContent-Disposition: form-data; name=\"imageFile\"; filename=\"esp32-cam.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";
    String tail = "\r\n--SendPhoto--\r\n";

    uint32_t imageLen = fb->len;
    uint32_t extraLen = head.length() + tail.length();
    uint32_t totalLen = imageLen + extraLen;
    String myPOST = "POST " + serverPath + " HTTP/1.1\r\n" + "Host: " + serverName + "\r\n" + "Content-Length: " + String(totalLen) + "\r\n" + "Content-Type: multipart/form-data; boundary=SendPhoto" + "\r\n\r\n";
    client.print(myPOST);
    client.flush();
    client.print(head);
    client.flush();
  
    uint8_t *fbBuf = fb->buf;
    size_t fbLen = fb->len;
    for (size_t n=0; n<fbLen; n=n+1024) {
      if (n+1024 < fbLen) {
        client.write(fbBuf, 1024);
        fbBuf += 1024;
      }
      else if (fbLen%1024>0) {
        size_t remainder = fbLen%1024;
        client.write(fbBuf, remainder);
      }
    }   
    client.print(tail);
    client.flush();
    esp_camera_fb_return(fb);
    
    int timoutTimer = 10000;
    long startTimer = millis();
    boolean state = false;
    
    while ((startTimer + timoutTimer) > millis()) {
      delay(100);      
      while (client.available()) {
        char c = client.read();
        if (c == '\n') {
          if (getAll.length()==0) { state=true; }
          getAll = "";
        }
        else if (c != '\r') {
          getAll += String(c); 
        }
        if (state==true) {
          getBody += String(c);
          }
        startTimer = millis();
      }
      if (getBody.length()>0) {
        break;
      }
    }
    client.stop();
    if (getBody.length() == 0) {
        return 2;
    }
  }
  else {
    return 1;
  }
  if(getBody == "OK"){
    return 0;
  }
}
