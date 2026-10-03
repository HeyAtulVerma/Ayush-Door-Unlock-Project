#include "arduino_secrets.h"

// With Cam

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_timer.h"
#include "img_converters.h"
#include "Arduino.h"
#include "fb_gfx.h"
#include "soc/soc.h" // Disable brownout problems
#include "soc/rtc_cntl_reg.h"  // Disable brownout problems
#include "esp_http_server.h"

// ================= USER SETTINGS =================
const char* ssid = "ayush";         // <--- PUT YOUR WIFI NAME
const char* password = "123123125";    // <--- PUT YOUR WIFI PASSWORD


 #define Relay Pin (GPIO 14)
// #define RELAY_PIN 14 
#define LED_PIN 4
// =================================================

#define PART_BOUNDARY "123456789000000000000987654321"

// CAMERA MODEL: AI THINKER
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
// #define LED_GPIO_NUM   4

// #if defined(LED_GPIO_NUM)
// #define CONFIG_LED_MAX_INTENSITY 255
// #endif


// #if defined(LED_GPIO_NUM)
//   ledcAttach(LED_GPIO_NUM, 5000, 8);
// #else
//   log_i("LED flash is disabled -> LED_GPIO_NUM undefined");
// #endif


static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t camera_httpd = NULL;

// HTML Page Code
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial; text-align: center; margin: 0px; padding: 20px; background-color: #222; color: white; }
    h2 { color: #f2f2f2; }
    .button { background-color: #4CAF50; border: none; color: white; padding: 15px 32px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 10px;}
    .stop { background-color: #f44336; }
    .lock-btn { background-color: #008CBA; padding: 20px 40px; font-size: 20px; font-weight: bold; margin-top: 20px; }
    img { width: 100%; max-width: 600px; height: auto; border: 2px solid #555; margin-top: 10px; }
  </style>
</head>
<body>
    <h2>ESP32-CAM Door Lock</h2>

    <img src="" id="photo">
    <br><br>

    <button class="button" onclick="startStream()">Start Camera</button>
    <button class="button stop" onclick="stopStream()">Stop Camera</button>

    <br><br>
    <hr>
    <label>Toggle LED:
        <input type="radio" id="led" name="color" value="Led" onclick="toggleLed('on')"> On
        <input type="radio" id="led" name="color" value="Led" onclick="toggleLed('off')"> Off
    </label>
    // <button class="button lock-btn" onclick="lockButton()">
    //     Click to UNLOCK
    // </button>

    <script>


        // Locking/Unlocking Mechanism
        let isUnlock = false;
        let autoLockTimer = null;

        function lockButton() {
            if (!isUnlock) {
                // ð UNLOCK
                unlock();
            } else {
                // ð MANUAL LOCK
                lock();
            }
        }

        // function unlock() {
        //     isUnlock = true;

        //     document.querySelector(".lock-btn").innerHTML = "UNLOCKED";
        //     document.querySelector(".lock-btn").style.backgroundColor = "#4CAF50";
        //     toggleLock('on');

        //     // Clear any existing timer
        //     clearTimeout(autoLockTimer);

        //     // Auto lock after 5 seconds
        //     autoLockTimer = setTimeout(() => {
        //         lock();
        //     }, 5000);
        // }

        function lock() {
            isUnlock = false;

            document.querySelector(".lock-btn").innerHTML = "Click to UNLOCK";
            document.querySelector(".lock-btn").style.backgroundColor = "#f44336";
            toggleLock('off');

            // Clear timer when locked manually
            clearTimeout(autoLockTimer);
            autoLockTimer = null;
        }

        function startStream() {
            document.getElementById("photo").src = "/stream";
        }

        function stopStream() {
            document.getElementById("photo").src = "";
        }

        function toggleLock(state) {
            const xhttp = new XMLHttpRequest();
            xhttp.open("GET", "/action?go=" + state, true);
            xhttp.send();
        }

        // LED toggle Mechanism



        function toggleLed(state) {
            console.log("LED State: " + state);
            const xhttp = new XMLHttpRequest();
            xhttp.open("GET", "/action?led=" + state, true);
            xhttp.send();
        }
    </script>
</body>
</html>
)rawliteral";

static esp_err_t index_handler(httpd_req_t *req){
  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, index_html, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t stream_handler(httpd_req_t *req){
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char * part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if(res != ESP_OK){
    return res;
  }

  while(true){
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Camera capture failed");
      res = ESP_FAIL;
    } else {
      if(fb->format != PIXFORMAT_JPEG){
        bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
        esp_camera_fb_return(fb);
        fb = NULL;
        if(!jpeg_converted){
          Serial.println("JPEG compression failed");
          res = ESP_FAIL;
        }
      } else {
        _jpg_buf_len = fb->len;
        _jpg_buf = fb->buf;
      }
    }
    if(res == ESP_OK){
      size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, _jpg_buf_len);
      res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
    }
    if(res == ESP_OK){
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }
    if(res == ESP_OK){
      res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    }
    if(fb){
      esp_camera_fb_return(fb);
      fb = NULL;
      _jpg_buf = NULL;
    } else if(_jpg_buf){
      free(_jpg_buf);
      _jpg_buf = NULL;
    }
    if(res != ESP_OK){
      break;
    }
  }
  return res;
}




static esp_err_t cmd_handler(httpd_req_t *req){
  char* buf;
  size_t buf_len;
  // char variable[32] = {0,};
  char led_variable[32] = {0,};
  
  buf_len = httpd_req_get_url_query_len(req) + 1;
  if (buf_len > 1) {
    buf = (char*)malloc(buf_len);
    if(!buf){
      httpd_resp_send_500(req);
      return ESP_FAIL;
    }
    if (httpd_req_get_url_query_str(req, buf, buf_len) == ESP_OK) {
      // if (httpd_query_key_value(buf, "go", variable, sizeof(variable)) == ESP_OK) {
      // }
      if (httpd_query_key_value(buf, "led", led_variable, sizeof(led_variable)) == ESP_OK) {
      }
    }
    free(buf);
  } else {
    httpd_resp_send_404(req);
    return ESP_FAIL;
  }

  // === Code for Lock/Unlock ===
  // if(!strcmp(variable, "on")) {
  //   digitalWrite(RELAY_PIN, LOW); // Keeps your logic: ON = LOW
  //   Serial.println("Lock OPEN");
  // }
  // else if(!strcmp(variable, "off")) {
  //   digitalWrite(RELAY_PIN, HIGH);
  //   Serial.println("Lock CLOSED");
  // }


  // // === Code for Led On/OFF ===
  if(!strcmp(led_variable, "true")) {
    digitalWrite(LED_PIN, HIGH); // Logic to turn on LED: ON = HIGH
    Serial.println("Led On");
  }
  else if(!strcmp(led_variable, "false")) {
    digitalWrite(LED_PIN, LOW);
    Serial.println("Led Off");
  }
  
  httpd_resp_send(req, NULL, 0);
  return ESP_OK;
}


void startCameraServer(){
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;

  httpd_uri_t index_uri = {
    .uri       = "/",
    .method    = HTTP_GET,
    .handler   = index_handler,
    .user_ctx  = NULL
  };

  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  httpd_uri_t cmd_uri = {
    .uri       = "/action",
    .method    = HTTP_GET,
    .handler   = cmd_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &index_uri);
    httpd_register_uri_handler(camera_httpd, &stream_uri);
    httpd_register_uri_handler(camera_httpd, &cmd_uri);
  }
}

void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); //disable brownout detector
  Serial.begin(115200);
  Serial.setDebugOutput(true);

  pinMode(LED_PIN, OUTPUT);
  // digitalWrite(RELAY_PIN, HIGH); // Start with lock closed

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

  // === ONLY CHANGE: Lower Resolution for Stability ===
  if(psramFound()){
    config.frame_size = FRAMESIZE_QVGA; // Changed to QVGA (320x240)
    config.jpeg_quality = 12;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA; // Changed to QVGA
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected");
  
  startCameraServer();

  Serial.print("Camera Ready! Use 'http://");
  Serial.print(WiFi.localIP());
  Serial.println("' to connect");
}

void loop() {
  delay(10000);
}