# -*- coding: utf-8 -*-
"""
超简单文字转语音 HTTP 服务
无需安装任何第三方库，只使用 Python 标准库
适配 ESP32 + MAX98357A 播放器
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request
import urllib.parse
import hashlib
import os
from datetime import datetime

# 配置
PORT = 5002
CACHE_DIR = "/tmp/tts_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# HTML 网页
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP32 文字转语音</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 600px;
            width: 100%;
        }
        h1 { color: #667eea; margin-bottom: 10px; font-size: 28px; }
        .subtitle { color: #666; margin-bottom: 30px; font-size: 14px; }
        textarea {
            width: 100%;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            resize: vertical;
            min-height: 120px;
            margin-bottom: 20px;
            font-family: inherit;
        }
        textarea:focus { outline: none; border-color: #667eea; }
        .btn-group { display: flex; gap: 10px; }
        button {
            flex: 1;
            padding: 15px;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn-primary { background: #667eea; color: white; }
        .btn-primary:hover {
            background: #5568d3;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .btn-secondary { background: #f0f0f0; color: #333; }
        .btn-secondary:hover { background: #e0e0e0; }
        .result {
            margin-top: 20px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            display: none;
        }
        .result.show { display: block; }
        .url-box {
            background: white;
            padding: 15px;
            border-radius: 8px;
            word-break: break-all;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            color: #667eea;
            margin: 10px 0;
            border: 2px dashed #667eea;
        }
        .copy-btn {
            background: #28a745;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 10px;
        }
        .copy-btn:hover { background: #218838; }
        audio { width: 100%; margin-top: 15px; }
        .info {
            background: #e7f3ff;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            font-size: 14px;
            color: #0066cc;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔊 ESP32 文字转语音</h1>
        <p class="subtitle">输入文字，生成 MP3 音频流（无需安装依赖版）</p>
        <textarea id="textInput" placeholder="请输入要转换的文字...&#10;例如：你好，欢迎使用 ESP32 语音播放器"></textarea>
        <div class="btn-group">
            <button class="btn-primary" onclick="generateTTS()">生成语音</button>
            <button class="btn-secondary" onclick="clearText()">清空</button>
        </div>
        <div id="result" class="result">
            <h3>✅ 生成成功</h3>
            <p><strong>HTTP 播放链接：</strong></p>
            <div class="url-box" id="urlBox"></div>
            <button class="copy-btn" onclick="copyURL()">📋 复制链接</button>
            <audio id="audioPlayer" controls></audio>
        </div>
        <div class="info">
            <strong>💡 使用说明：</strong><br>
            1. 输入文字后点击"生成语音"<br>
            2. 复制生成的 HTTP 链接<br>
            3. 粘贴到 ESP32 代码的 MP3_URL 中<br>
            4. 重新上传代码即可播放
        </div>
    </div>
    <script>
        function generateTTS() {
            const text = document.getElementById('textInput').value.trim();
            if (!text) { alert('请输入文字！'); return; }
            fetch('/api/tts', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: text})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    const url = window.location.origin + data.url;
                    document.getElementById('urlBox').textContent = url;
                    document.getElementById('audioPlayer').src = data.url;
                    document.getElementById('result').classList.add('show');
                } else {
                    alert('生成失败：' + data.error);
                }
            })
            .catch(err => { alert('请求失败：' + err); });
        }
        function copyURL() {
            const url = document.getElementById('urlBox').textContent;
            navigator.clipboard.writeText(url).then(() => {
                alert('✅ 链接已复制到剪贴板！');
            });
        }
        function clearText() {
            document.getElementById('textInput').value = '';
            document.getElementById('result').classList.remove('show');
        }
    </script>
</body>
</html>"""

class TTSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        
        elif self.path.startswith('/audio/'):
            filename = self.path.split('/')[-1]
            filepath = os.path.join(CACHE_DIR, filename)
            
            if os.path.exists(filepath):
                self.send_response(200)
                self.send_header('Content-type', 'audio/mpeg')
                self.send_header('Content-Length', str(os.path.getsize(filepath)))
                self.end_headers()
                with open(filepath, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'File not found')
        
        elif self.path.startswith('/api/tts'):
            # GET 方式调用 TTS，参数在 URL 中
            try:
                print(f"[{datetime.now()}] 收到 GET 请求: {self.path}")
                
                # 解析 URL 参数
                from urllib.parse import parse_qs, urlparse
                parsed = urlparse(self.path)
                
                # 如果没有查询参数，返回错误
                if not parsed.query:
                    print(f"[{datetime.now()}] 错误: 缺少查询参数")
                    self.send_json_response({'success': False, 'error': '缺少 text 参数'})
                    return
                
                params = parse_qs(parsed.query)
                text = params.get('text', [''])[0]
                
                print(f"[{datetime.now()}] 解析到文字: {text}")
                
                if not text:
                    print(f"[{datetime.now()}] 错误: 文字为空")
                    self.send_json_response({'success': False, 'error': '文字不能为空'})
                    return
                
                # 生成 MP3
                text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
                mp3_filename = f"{text_hash}.mp3"
                mp3_path = os.path.join(CACHE_DIR, mp3_filename)
                
                print(f"[{datetime.now()}] 文件名: {mp3_filename}")
                
                if not os.path.exists(mp3_path):
                    print(f"[{datetime.now()}] 缓存不存在，开始生成...")
                    try:
                        tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=zh-CN&client=tw-ob&q={urllib.parse.quote(text)}"
                        print(f"[{datetime.now()}] Google TTS URL: {tts_url}")
                        
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                            'Referer': 'https://translate.google.com/'
                        }
                        req = urllib.request.Request(tts_url, headers=headers)
                        
                        print(f"[{datetime.now()}] 正在请求 Google TTS...")
                        with urllib.request.urlopen(req, timeout=15) as response:
                            audio_data = response.read()
                            print(f"[{datetime.now()}] 收到数据: {len(audio_data)} 字节")
                            
                            if len(audio_data) > 0:
                                with open(mp3_path, 'wb') as f:
                                    f.write(audio_data)
                                print(f"[{datetime.now()}] 生成新语音: {text[:30]}... (大小: {len(audio_data)} 字节)")
                            else:
                                raise Exception("音频数据为空")
                    except Exception as e:
                        print(f"[ERROR] Google TTS 失败: {e}")
                        import traceback
                        traceback.print_exc()
                        self.send_json_response({'success': False, 'error': f'TTS 生成失败: {str(e)}'})
                        return
                else:
                    print(f"[{datetime.now()}] 使用缓存: {text[:30]}...")
                
                # 返回完整的 MP3 URL
                host = self.headers.get('Host', f'localhost:{PORT}')
                mp3_url = f"http://{host}/audio/{mp3_filename}"
                print(f"[{datetime.now()}] 返回 URL: {mp3_url}")
                
                self.send_json_response({
                    'success': True,
                    'url': mp3_url,
                    'text': text
                })
            except Exception as e:
                print(f"[ERROR] 处理请求失败: {e}")
                import traceback
                traceback.print_exc()
                self.send_json_response({'success': False, 'error': str(e)})
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/api/tts':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                text = data.get('text', '').strip()
                
                if not text:
                    self.send_json_response({'success': False, 'error': '文字不能为空'})
                    return
                
                # 生成文件名
                text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
                mp3_filename = f"{text_hash}.mp3"
                mp3_path = os.path.join(CACHE_DIR, mp3_filename)
                
                # 如果缓存不存在，从 Google TTS 下载
                if not os.path.exists(mp3_path):
                    try:
                        # 使用 Google TTS API
                        tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=zh-CN&client=tw-ob&q={urllib.parse.quote(text)}"
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        req = urllib.request.Request(tts_url, headers=headers)
                        
                        with urllib.request.urlopen(req, timeout=10) as response:
                            with open(mp3_path, 'wb') as f:
                                f.write(response.read())
                        
                        print(f"[{datetime.now()}] 生成新语音: {text[:30]}...")
                    except Exception as e:
                        print(f"[ERROR] 生成失败: {e}")
                        self.send_json_response({'success': False, 'error': f'生成失败: {str(e)}'})
                        return
                else:
                    print(f"[{datetime.now()}] 使用缓存: {text[:30]}...")
                
                self.send_json_response({
                    'success': True,
                    'url': f'/audio/{mp3_filename}',
                    'text': text
                })
            
            except Exception as e:
                print(f"[ERROR] {e}")
                self.send_json_response({'success': False, 'error': str(e)})
        else:
            self.send_response(404)
            self.end_headers()
    
    def send_json_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def log_message(self, format, *args):
        print(f"[{datetime.now()}] {format % args}")

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), TTSHandler)
    print("=" * 60)
    print("ESP32 文字转语音服务启动（无依赖版本）")
    print(f"访问: http://127.0.0.1:{PORT}")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.shutdown()
