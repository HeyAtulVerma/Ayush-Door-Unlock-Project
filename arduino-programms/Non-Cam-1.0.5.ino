#include "arduino_secrets.h"

// Non-Cam

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

// Relay Pin (GPIO 14)
#define BUTTON_PIN 2
#define TOUCH_INPUT_PIN 12
#define MAGNETIC_INPUT 13
#define RELAY_PIN 14 
#define BUZZER_ACTIVATION_PIN 15

IPAddress SECOND_IP;


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

bool canBeep = true;
bool isLocked = true;
unsigned long unlockTime = 0;
const unsigned long autoLockDelay = 5000;

static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t camera_httpd = NULL;

// HTML Page Code
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">

<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Open Close UI</title>

    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: Arial, sans-serif;
        }

        /* The switch - the box around the slider */
        .switch {
            position: relative;
            display: inline-block;
            width: 60px;
            height: 34px;
        }

        /* Hide default HTML checkbox */
        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        /* The slider */
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #ccc;
            -webkit-transition: .4s;
            transition: .4s;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 26px;
            width: 26px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            -webkit-transition: .4s;
            transition: .4s;
        }

        input:checked+.slider {
            background-color: #2196F3;
        }

        input:focus+.slider {
            box-shadow: 0 0 1px #2196F3;
        }

        input:checked+.slider:before {
            -webkit-transform: translateX(26px);
            -ms-transform: translateX(26px);
            transform: translateX(26px);
        }

        /* Rounded sliders */
        .slider.round {
            border-radius: 34px;
        }

        .slider.round:before {
            border-radius: 50%;
        }

        body {
            display: flex;
            flex-direction: column;
            align-items: center;
            /* justify-content: center; */
            height: 100vh;
            background: #151515;
        }

        .btn-green {
            background-color: rgb(196, 252, 196);
            color: rgb(0, 149, 0);
        }

        .btn-red {
            background-color: rgb(252, 196, 196);
            color: rgb(149, 0, 0);
        }

        .video-container {
            /* width: fit-content; */
            border: 2px solid white;
            overflow: hidden;
            max-width: 500px;
            width: 100vw;
            aspect-ratio: 4/3;
            border-radius: 12px;

        }

        .video {
            max-width: 500px;
            width: 100vw;
        }

        .toggle-container {
            margin: 15px 0;
            width: 200px;
            color: white;
            display: flex;
            justify-content: space-between;
            justify-items: center;
            align-items: center;
            font-size: 20px;
            gap: 20px;
        }

        .controls {
            gap: 10px;
            padding: 10px;
            display: flex;
            justify-content: space-between;
        }
    </style>

</head>

<body>

    <div class="container">
        <div class="video-container" style="position: relative;">

            <div style="
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                color: #ccc;
                z-index: -10;
            " id="camera-status-text">
                Camera Off
            </div>

            <img src="" alt="" class="video" id="video">
        </div>
        <div class="controls">
            <div>
                <button id="lock-button" onclick="toggleLock()"
                    style="width: 200px; height: 100%; font-size: 25px; font-weight: 800; cursor: pointer;">Locked</button>
            </div>

            <div>
                <div class="toggle-container">
                    <span>
                        Camera
                    </span>

                    <label class="switch">
                        <input type="checkbox" id="camera">
                        <span class="slider round"></span>
                    </label>
                </div>

                <div class="toggle-container">
                    <span>
                        Flash
                    </span>

                    <label class="switch">
                        <input type="checkbox" id="flash">
                        <span class="slider round"></span>
                    </label>
                </div>
            </div>
        </div>
    </div>

    </div>




    <script>
        let isLocked = true;
        let lastClickTime = 0;

        let secondIP = "%IP%";
        
        const parts = secondIP.split(".");
        const firstThree = parts.slice(0, 3).join(".");
        console.log("IP for python code: "+firstThree+".222"); 

        const video = document.getElementById("video");
        const cameraStatusText = document.getElementById("camera-status-text");

        const lockButton = document.getElementById("lock-button");

        const cameraSwitch = document.getElementById("camera");
        const flashSwitch = document.getElementById("flash");


        cameraSwitch.addEventListener("change", function () {
            if (this.checked) {
                cameraStatusText.innerText = "Turning on..."
                video.src = "http://"+secondIP+"/stream";
            } else {
                video.src = ""
                cameraStatusText.innerText = "Camera Off"
            }
        });
        flashSwitch.addEventListener("change", function () {
            const xhttp = new XMLHttpRequest();
            xhttp.open("GET", `http://${secondIP}/action?led=${this.checked}`, true);
            xhttp.send();
        });

        const toggleLock = () => {
            const xhttp = new XMLHttpRequest();
            console.log(secondIP)
            lastClickTime = Date.now();


            if (!isLocked) {
                xhttp.open("GET", `/action?go=false`, true);
                

            } else {
                xhttp.open("GET", `/action?go=true`, true);
            }
            updateUi(!isLocked);
            xhttp.send();

        };

        

        function updateUi(isLock){
          if(isLock){
                lockButton.innerText = "Locked";
                lockButton.classList.add("btn-red");
                lockButton.classList.remove("btn-green");
          }else{
                lockButton.innerText = "Unlocked";
                lockButton.classList.add("btn-green");
                lockButton.classList.remove("btn-red");
          }
          
        }

        function updateStatus(){
          fetch("/status")
          .then(res => res.json())
          .then(data=>{
            isLocked = data.status == 0 ? false : true;
            console.log(data);
          });

          if (Date.now() - lastClickTime <= 2000) return;

          updateUi(isLocked);
        }

        setInterval(updateStatus, 1000);
    </script>
</body>

</html>
)rawliteral";

void lock(){
  // canBeep = true;
  isLocked = true;
  digitalWrite(RELAY_PIN, HIGH);
  Serial.println("locked");

}

void unlock(){
  unlockTime = millis();
  isLocked = false;
  canBeep = false;
  digitalWrite(RELAY_PIN, LOW);
  Serial.println("unlocked");
  
}

static esp_err_t index_handler(httpd_req_t *req){
  httpd_resp_set_type(req, "text/html");
  String html = index_html;   // PROGMEM â RAM
  html.replace("%IP%", SECOND_IP.toString());

  return httpd_resp_send(req, html.c_str(), html.length());
}


static esp_err_t cmd_handler(httpd_req_t *req){
char* buf;
  size_t buf_len;
  char variable[32] = {0,};
  
  buf_len = httpd_req_get_url_query_len(req) + 1;
  if (buf_len > 1) {
    buf = (char*)malloc(buf_len);
    if(!buf){
      httpd_resp_send_500(req);
      return ESP_FAIL;
    }
    if (httpd_req_get_url_query_str(req, buf, buf_len) == ESP_OK) {
      if (httpd_query_key_value(buf, "go", variable, sizeof(variable)) == ESP_OK) {
      }
    }
    free(buf);
  } else {
    httpd_resp_send_404(req);
    return ESP_FAIL;
  }

  if(!strcmp(variable, "true")) {
    unlock();
  }
  else if(!strcmp(variable, "false")) {
    lock();
  }
  
  httpd_resp_send(req, NULL, 0);
  return ESP_OK;
}

static esp_err_t status_handler(httpd_req_t *req){
  char response[100];
  snprintf(response, sizeof(response), 
  "{\"status\":\"%d\"}",
  isLocked
  );

  httpd_resp_set_type(req, "application/json");
  httpd_resp_send(req, response, strlen(response));
  return ESP_OK;
}

void startServer(){
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;

  httpd_uri_t index_uri = {
    .uri       = "/",
    .method    = HTTP_GET,
    .handler   = index_handler,
    .user_ctx  = NULL
  };

  httpd_uri_t status_uri = {
    .uri       = "/status",
    .method    = HTTP_GET,
    .handler   = status_handler,
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
    httpd_register_uri_handler(camera_httpd, &cmd_uri);
    httpd_register_uri_handler(camera_httpd, &status_uri);

  }
}


void startBeep(){
if(canBeep){
  digitalWrite(BUZZER_ACTIVATION_PIN, HIGH);
  delay(400);
}
}

void stopBeep(){
  digitalWrite(BUZZER_ACTIVATION_PIN, LOW);
}


void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); //disable brownout detector
  Serial.begin(115200);
  Serial.setDebugOutput(true);

  pinMode(MAGNETIC_INPUT, INPUT_PULLUP);  // input
  pinMode(TOUCH_INPUT_PIN, INPUT_PULLUP);  // input
  pinMode(BUZZER_ACTIVATION_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);  // internal pull-up
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH); // Start with lock closed

  

  WiFi.disconnect(true);
  delay(1000);
  WiFi.begin(ssid, password);
    Serial.print("Connecting.");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected");
  
  startServer();

  Serial.print("Camera Ready! Use 'http://");
  SECOND_IP = WiFi.localIP();
  SECOND_IP[3] = 43;

  Serial.print(SECOND_IP);

  Serial.println("' to connect");
}

void loop() {

  if(!canBeep && millis()-unlockTime >= autoLockDelay){
    if (digitalRead(MAGNETIC_INPUT) == LOW){
      canBeep = true;
    }

  }

   if(!isLocked && millis()-unlockTime >= autoLockDelay){
    lock();
    Serial.println("Auto Locked!");
  }


  if (digitalRead(MAGNETIC_INPUT) == HIGH){
    startBeep();
    
  }else{
    Serial.println("nobeep");
    stopBeep();
  }


  if (digitalRead(BUTTON_PIN) == LOW) {
    // Button is pressed
    Serial.println("Button PRESSED - Action ON");
    unlock(); 

  }

  if(digitalRead(TOUCH_INPUT_PIN) == HIGH ){
    startBeep();
  }else{
    stopBeep();
  }

  delay(100); // debounce + CPU friendly
}


