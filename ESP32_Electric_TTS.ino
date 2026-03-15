/*
 * ESP32 电费查询语音播放器 - 完整重构版
 * 
 * 功能：
 * 1. 余额低于10元时播报
 * 2. 每天 12:30 和 22:55 定时播报
 * 3. 每个整点和半点播报（如 1:00, 1:30, 2:00, 2:30...）
 * 4. 按 BOOT 键手动播报
 * 5. WiFi 信号异常时语音提醒
 * 
 * 硬件连接：
 * MAX98357A DIN  → GPIO25
 * MAX98357A BCLK → GPIO26
 * MAX98357A LRC  → GPIO27
 * BOOT 按键      → GPIO0（板载）
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include "AudioFileSourceHTTPStream.h"
#include "AudioFileSourceBuffer.h"
#include "AudioGeneratorMP3.h"
#include "AudioOutputI2S.h"

// ==================== 配置区域 ====================
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// 电费查询接口
const char* BALANCE_API = "http://127.0.0.1:16888/api/balance/room1";

// TTS 接口
const char* TTS_API = "http://127.0.0.1:5002/api/tts";

// 时间服务器接口
const char* TIME_API = "http://127.0.0.1:5001/api/time";

// I2S 引脚  原本！！！！！！
#define I2S_BCLK  26
#define I2S_LRC   27
#define I2S_DOUT  25
// //I2S 引脚
// #define I2S_BCLK  48
// #define I2S_LRC   47
// #define I2S_DOUT  21
// BOOT 按键引脚
#define BOOT_PIN  0

// 音量设置
const float VOLUME_GAIN = 0.35f;

// 低电费阈值
const float LOW_BALANCE_THRESHOLD = 10.0f;

// WiFi 信号健康阈值（dBm）
const int WIFI_SIGNAL_THRESHOLD = -70;
// ==================================================

// 音频对象
AudioGeneratorMP3* mp3 = nullptr;
AudioFileSourceHTTPStream* audioStream = nullptr;
AudioOutputI2S* audioOut = nullptr;

// 时间相关
unsigned long timeOffset = 0;  // 时间偏移量（秒）
unsigned long lastTimeSyncMillis = 0;
bool timeInitialized = false;

// 状态变量
float currentBalance = 0.0f;
float lastReportedBalance = -1.0f;  // 上次播报的电费
String currentRoom = "";
int lastReportedMinute = -1;  // 上次播报的分钟数
bool last1230Reported = false;
bool last2255Reported = false;
unsigned long lastBalanceCheckTime = 0;
const unsigned long BALANCE_CHECK_INTERVAL = 1800000;  // 30分钟
bool balanceQuerySuccess = false;  // 电费查询是否成功

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n========================================");
  Serial.println("ESP32 智能电费播报器 v2.0");
  Serial.println("========================================\n");

  // 初始化 BOOT 按键
  pinMode(BOOT_PIN, INPUT_PULLUP);

  // 初始化 I2S 音频输出
  audioOut = new AudioOutputI2S(0, 1); // 使用内部 DAC 端口 0，DMA 缓冲区 1
  audioOut->SetPinout(I2S_BCLK, I2S_LRC, I2S_DOUT);
  audioOut->SetGain(VOLUME_GAIN);
  audioOut->SetOutputModeMono(false); // 立体声输出
  Serial.println("[Audio] I2S 初始化完成");
  Serial.print("[Audio] BCLK=");
  Serial.print(I2S_BCLK);
  Serial.print(", LRC=");
  Serial.print(I2S_LRC);
  Serial.print(", DOUT=");
  Serial.println(I2S_DOUT);

  // 连接 WiFi
  connectWiFi();
  
  // 同步时间
  Serial.println("[时间] 正在同步时间...");
  syncTime();
  printCurrentTime();

  // 获取电费信息
  updateBalanceInfo();
  
  // 检查 WiFi 信号
  checkWiFiSignal();
  
  Serial.println("\n[系统] 初始化完成，开始运行\n");
}

void loop() {
  unsigned long currentMillis = millis();
  
  // 检查 BOOT 按键
  static bool lastButtonState = HIGH;
  bool currentButtonState = digitalRead(BOOT_PIN);
  
  if (lastButtonState == HIGH && currentButtonState == LOW) {
    delay(50);  // 消抖
    if (digitalRead(BOOT_PIN) == LOW) {
      Serial.println("\n[按键] 手动播报");
      updateBalanceInfo();
      playBalanceAudio(true);
    }
  }
  lastButtonState = currentButtonState;
  
  // 每30分钟更新一次
  if (currentMillis - lastBalanceCheckTime >= BALANCE_CHECK_INTERVAL) {
    lastBalanceCheckTime = currentMillis;
    Serial.println("\n[定时] 30分钟更新");
    updateBalanceInfo();
    checkWiFiSignal();
    syncTime();
  }
  
  // 每秒检查时间
  static unsigned long lastSecondCheck = 0;
  if (currentMillis - lastSecondCheck >= 1000) {
    lastSecondCheck = currentMillis;
    checkTimeAndPlay();
  }
  
  delay(50);
}

// 连接 WiFi
void connectWiFi() {
  Serial.print("[WiFi] 连接中: ");
  Serial.println(WIFI_SSID);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WiFi] ✓ 连接成功");
    Serial.print("[WiFi] IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("[WiFi] 信号: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
  } else {
    Serial.println("[WiFi] ✗ 连接失败，重启...");
    delay(3000);
    ESP.restart();
  }
}

// 检查 WiFi 信号
void checkWiFiSignal() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] ✗ 断开连接");
    connectWiFi();
    return;
  }
  
  int rssi = WiFi.RSSI();
  Serial.print("[WiFi] 信号强度: ");
  Serial.print(rssi);
  Serial.println(" dBm");
  
  if (rssi < WIFI_SIGNAL_THRESHOLD) {
    Serial.println("[WiFi] ⚠ 信号弱");
  }
}

// 同步时间（从 HTTP 服务器）
void syncTime() {
  HTTPClient http;
  http.begin(TIME_API);
  http.setTimeout(5000);
  
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    String payload = http.getString();
    
    DynamicJsonDocument doc(512);
    DeserializationError error = deserializeJson(doc, payload);
    
    if (!error && doc["success"] == true) {
      unsigned long timestamp = doc["timestamp"];
      timeOffset = timestamp - (millis() / 1000);
      lastTimeSyncMillis = millis();
      timeInitialized = true;
      
      Serial.println("[时间] ✓ 同步成功");
      Serial.print("[时间] ");
      Serial.println(doc["datetime"].as<String>());
    } else {
      Serial.println("[时间] ✗ 解析失败");
    }
  } else {
    Serial.print("[时间] ✗ HTTP: ");
    Serial.println(httpCode);
  }
  
  http.end();
}

// 获取当前时间
bool getCurrentTime(int& hour, int& minute, int& second) {
  if (!timeInitialized) {
    return false;
  }
  
  // 计算当前时间戳
  unsigned long currentTimestamp = timeOffset + (millis() / 1000);
  
  // 加上北京时区偏移（UTC+8 = 28800秒）
  currentTimestamp += 28800;
  
  // 转换为时分秒
  unsigned long secondsInDay = currentTimestamp % 86400;
  hour = secondsInDay / 3600;
  minute = (secondsInDay % 3600) / 60;
  second = secondsInDay % 60;
  
  return true;
}

// 打印当前时间
void printCurrentTime() {
  int hour, minute, second;
  if (!getCurrentTime(hour, minute, second)) {
    Serial.println("[时间] 获取失败");
    return;
  }
  
  char timeStr[32];
  sprintf(timeStr, "%02d:%02d:%02d", hour, minute, second);
  Serial.print("[时间] ");
  Serial.println(timeStr);
}

// 检查时间并播报
void checkTimeAndPlay() {
  int hour, minute, second;
  if (!getCurrentTime(hour, minute, second)) {
    return;
  }
  
  // 每分钟打印时间
  if (second == 0) {
    printCurrentTime();
  }
  
  // 只在整分钟触发
  if (second != 0) {
    return;
  }
  
  // 检查是否是整点或半点（0分或30分）
  if (minute != 0 && minute != 30) {
    return;
  }
  
  // 避免重复播报同一分钟
  if (lastReportedMinute == minute) {
    return;
  }
  
  bool shouldPlay = false;
  String reason = "";
  
  // 1. 余额不足（每次都播报）
  if (currentBalance > 0 && currentBalance < LOW_BALANCE_THRESHOLD) {
    shouldPlay = true;
    reason = "余额不足";
  }
  
  // 2. 12:30 定时播报
  if (hour == 12 && minute == 30) {
    if (!last1230Reported) {
      shouldPlay = true;
      reason = "12:30定时";
      last1230Reported = true;
    }
  } else {
    last1230Reported = false;
  }
  
  // 3. 22:55 定时播报（改为22:30）
  if (hour == 22 && minute == 30) {
    if (!last2255Reported) {
      shouldPlay = true;
      reason = "22:30定时";
      last2255Reported = true;
    }
  } else {
    last2255Reported = false;
  }
  
  // 4. 每30分钟播报时间（整点和半点）
  if (!shouldPlay) {
    shouldPlay = true;
    reason = "30分钟播报";
  }
  
  // 执行播报
  if (shouldPlay) {
    Serial.print("\n[播报] ");
    Serial.println(reason);
    
    lastReportedMinute = minute;
    
    // 先更新电费信息
    updateBalanceInfo();
    
    // 播报时间和电费
    playTimeAndBalance(hour, minute);
  }
}

// 更新电费信息
void updateBalanceInfo() {
  Serial.println("[电费] 查询中...");
  
  balanceQuerySuccess = false;  // 重置查询状态
  
  HTTPClient http;
  http.begin(BALANCE_API);
  http.setTimeout(10000);
  
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    String payload = http.getString();
    
    DynamicJsonDocument doc(1024);
    DeserializationError error = deserializeJson(doc, payload);
    
    if (!error && doc["status"] == "success") {
      currentRoom = doc["room"].as<String>();
      currentBalance = doc["balance"];
      balanceQuerySuccess = true;  // 查询成功
      
      Serial.print("[电费] 房间: ");
      Serial.print(currentRoom);
      Serial.print(" | 余额: ");
      Serial.print(currentBalance, 1);
      Serial.println(" 元");
    } else {
      Serial.println("[电费] ✗ 解析失败");
    }
  } else {
    Serial.print("[电费] ✗ 请求失败: ");
    Serial.println(httpCode);
  }
  
  http.end();
}

// 播放时间和电费
void playTimeAndBalance(int hour, int minute) {
  // 播报时间
  String timeText = "现在时间是";
  
  if (hour == 0) {
    timeText += "零点";
  } else {
    timeText += String(hour) + "点";
  }
  
  if (minute > 0) {
    timeText += String(minute) + "分";
  }
  
  playTTSAudio(timeText);
  delay(1000);
  
  // 只有在电费查询成功时才播报电费
  if (!balanceQuerySuccess) {
    Serial.println("[电费] 查询失败，跳过电费播报");
    return;
  }
  
  // 检查电费是否有变化
  bool balanceChanged = (lastReportedBalance < 0 || 
                         abs(currentBalance - lastReportedBalance) > 0.01);
  
  if (balanceChanged) {
    // 电费有变化，播报电费
    Serial.println("[电费] 电费有变化，播报");
    playBalanceAudio(false);
    lastReportedBalance = currentBalance;
  } else {
    // 电费没变化，跳过
    Serial.println("[电费] 电费无变化，跳过播报");
  }
}

// 播放电费语音
void playBalanceAudio(bool forcePlay) {
  if (currentBalance <= 0 && !forcePlay) {
    Serial.println("[播报] 无效余额，跳过");
    return;
  }
  
  String formattedRoom = formatRoomNumber(currentRoom);
  String text = formattedRoom + "，当前剩余电费" + String(currentBalance, 1) + "元";
  
  if (currentBalance < LOW_BALANCE_THRESHOLD) {
    text += "，余额不足，请及时充值";
  }
  
  playTTSAudio(text);
}

// 播放 TTS 语音
void playTTSAudio(String text) {
  Serial.print("[TTS] 内容: ");
  Serial.println(text);
  
  String mp3Url = generateTTS(text);
  if (mp3Url.length() == 0) {
    Serial.println("[TTS] ✗ 生成失败");
    return;
  }
  
  playAudio(mp3Url);
}

// 格式化房间号
String formatRoomNumber(String room) {
  int dashIndex = room.indexOf('-');
  if (dashIndex == -1 || dashIndex + 5 > room.length()) {
    return room;
  }
  
  String prefix = room.substring(0, dashIndex);
  String roomNum = room.substring(dashIndex + 1);
  
  if (roomNum.length() == 4) {
    String roomPart = roomNum.substring(0, 3);
    String bedPart = roomNum.substring(3, 4);
    return prefix + roomPart + "室" + bedPart + "房";
  }
  
  return room;
}

// 生成 TTS
String generateTTS(String text) {
  HTTPClient http;
  String encodedText = urlEncode(text);
  String ttsUrl = String(TTS_API) + "?text=" + encodedText;
  
  http.begin(ttsUrl);
  http.setTimeout(15000);
  
  int httpCode = http.GET();
  String mp3Url = "";
  
  if (httpCode == 200) {
    String payload = http.getString();
    
    DynamicJsonDocument doc(1024);
    DeserializationError error = deserializeJson(doc, payload);
    
    if (!error && doc["success"] == true) {
      mp3Url = doc["url"].as<String>();
      Serial.print("[TTS] URL: ");
      Serial.println(mp3Url);
    } else {
      Serial.println("[TTS] ✗ JSON 错误");
    }
  } else {
    Serial.print("[TTS] ✗ HTTP: ");
    Serial.println(httpCode);
  }
  
  http.end();
  return mp3Url;
}

// URL 编码
String urlEncode(String str) {
  String encoded = "";
  char c;
  char code0;
  char code1;
  
  for (int i = 0; i < str.length(); i++) {
    c = str.charAt(i);
    if (c == ' ') {
      encoded += '+';
    } else if (isalnum(c)) {
      encoded += c;
    } else {
      code1 = (c & 0xf) + '0';
      if ((c & 0xf) > 9) {
        code1 = (c & 0xf) - 10 + 'A';
      }
      c = (c >> 4) & 0xf;
      code0 = c + '0';
      if (c > 9) {
        code0 = c - 10 + 'A';
      }
      encoded += '%';
      encoded += code0;
      encoded += code1;
    }
  }
  return encoded;
}

// 播放音频
void playAudio(String url) {
  // 清理旧对象
  if (mp3) {
    if (mp3->isRunning()) mp3->stop();
    delete mp3;
    mp3 = nullptr;
  }
  if (audioStream) {
    delete audioStream;
    audioStream = nullptr;
  }
  
  Serial.println("[Audio] 播放中...");
  
  // 创建音频流
  audioStream = new AudioFileSourceHTTPStream(url.c_str());
  mp3 = new AudioGeneratorMP3();
  
  // 开始播放
  if (mp3->begin(audioStream, audioOut)) {
    while (mp3->isRunning()) {
      if (!mp3->loop()) {
        mp3->stop();
        break;
      }
      delay(1);
    }
    Serial.println("[Audio] ✓ 完成");
  } else {
    Serial.println("[Audio] ✗ 失败");
  }
  
  // 清理
  if (mp3) {
    mp3->stop();
    delete mp3;
    mp3 = nullptr;
  }
  if (audioStream) {
    delete audioStream;
    audioStream = nullptr;
  }
}
