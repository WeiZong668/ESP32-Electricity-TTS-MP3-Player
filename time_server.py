#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的时间服务器
提供北京时间的 Unix 时间戳
"""

from flask import Flask, jsonify
from datetime import datetime
import pytz

app = Flask(__name__)

@app.route('/api/time', methods=['GET'])
def get_time():
    """返回北京时间的 Unix 时间戳"""
    # 获取北京时区
    beijing_tz = pytz.timezone('Asia/Shanghai')
    
    # 获取当前北京时间
    beijing_time = datetime.now(beijing_tz)
    
    # 转换为 Unix 时间戳
    timestamp = int(beijing_time.timestamp())
    
    # 返回 JSON 格式
    return jsonify({
        'success': True,
        'timestamp': timestamp,
        'datetime': beijing_time.strftime('%Y-%m-%d %H:%M:%S'),
        'timezone': 'Asia/Shanghai'
    })

@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    # 监听所有网络接口，端口 5001
    app.run(host='0.0.0.0', port=5001, debug=False)
