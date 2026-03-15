"""
校园水电查询 Web API 服务
用于部署到服务器，提供HTTP接口供ESP32等设备调用
"""
import sys
import os

# 确保可以导入当前目录的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request
from flask_cors import CORS
from campus_crawler import CampusElectricCrawler
import json
import time
from functools import wraps

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 配置信息
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    # 默认占位配置，用户需在 ESP32_Electric_TTS/config.json 中填写自己的配置
    return {
        'account': 'YOUR_ACCOUNT',
        'customercode': 'YOUR_SCHOOL_CODE',
        'rooms': [
            {'id': 'room1', 'name': '你的校区-楼栋-房间', 'roomverify': 'ROOM_VERIFY_CODE'}
        ]
    }

CONFIG = load_config()

# 创建爬虫实例
crawler = CampusElectricCrawler()

# 缓存机制（避免频繁请求）
cache = {}
CACHE_EXPIRE = 300  # 缓存5分钟


def cache_result(expire_time=CACHE_EXPIRE):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}_{args}_{kwargs}"
            current_time = time.time()
            
            # 检查缓存
            if cache_key in cache:
                cached_data, cached_time = cache[cache_key]
                if current_time - cached_time < expire_time:
                    return cached_data
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache[cache_key] = (result, current_time)
            return result
        return wrapper
    return decorator


@app.route('/')
def index():
    """API首页"""
    return jsonify({
        'status': 'success',
        'message': '校园水电查询API',
        'version': '1.0',
        'endpoints': {
            '/api/rooms': '获取所有房间列表',
            '/api/query/<room_id>': '查询指定房间电费',
            '/api/query_all': '查询所有房间电费',
            '/api/balance/<room_id>': '只返回余额（简化版）'
        }
    })


@app.route('/api/rooms', methods=['GET'])
def get_rooms():
    """获取所有房间列表"""
    rooms_info = []
    for room in CONFIG['rooms']:
        rooms_info.append({
            'id': room['id'],
            'name': room['name'],
            'roomverify': room['roomverify']
        })
    
    return jsonify({
        'status': 'success',
        'count': len(rooms_info),
        'rooms': rooms_info
    })


@app.route('/api/query/<room_id>', methods=['GET'])
@cache_result(expire_time=300)
def query_room(room_id):
    """查询指定房间的电费"""
    # 查找房间
    room = None
    for r in CONFIG['rooms']:
        if r['id'] == room_id:
            room = r
            break
    
    if not room:
        return jsonify({
            'status': 'error',
            'message': f'房间ID {room_id} 不存在'
        }), 404
    
    # 查询电费
    try:
        result = crawler.get_room_info(
            account=CONFIG['account'],
            customercode=CONFIG['customercode'],
            roomverify=room['roomverify']
        )
        
        if result['success']:
            return jsonify({
                'status': 'success',
                'room_id': room_id,
                'room_name': result['room_full_name'],
                'room_number': result['room_number'],
                'balance': result['electric']['balance'],
                'device_name': result['electric']['device_name'],
                'total_purchased': result['electric']['total_purchased'],
                'total_subsidy': result['electric']['total_subsidy'],
                'daily_usage': result['electric'].get('daily_usage', []),
                'timestamp': int(time.time())
            })
        else:
            return jsonify({
                'status': 'error',
                'message': result['message']
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500


@app.route('/api/balance/<room_id>', methods=['GET'])
@cache_result(expire_time=300)
def get_balance(room_id):
    """只返回余额（简化版，适合ESP32）"""
    # 查找房间
    room = None
    for r in CONFIG['rooms']:
        if r['id'] == room_id:
            room = r
            break
    
    if not room:
        return jsonify({
            'status': 'error',
            'balance': 0
        }), 404
    
    # 查询电费
    try:
        result = crawler.get_room_info(
            account=CONFIG['account'],
            customercode=CONFIG['customercode'],
            roomverify=room['roomverify']
        )
        
        if result['success']:
            return jsonify({
                'status': 'success',
                'balance': result['electric']['balance'],
                'room': result['room_full_name']
            })
        else:
            return jsonify({
                'status': 'error',
                'balance': 0
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'balance': 0
        }), 500


@app.route('/api/query_all', methods=['GET'])
@cache_result(expire_time=300)
def query_all_rooms():
    """查询所有房间的电费"""
    results = []
    
    for room in CONFIG['rooms']:
        try:
            result = crawler.get_room_info(
                account=CONFIG['account'],
                customercode=CONFIG['customercode'],
                roomverify=room['roomverify']
            )
            
            if result['success']:
                results.append({
                    'room_id': room['id'],
                    'room_name': result['room_full_name'],
                    'balance': result['electric']['balance'],
                    'status': 'success'
                })
            else:
                results.append({
                    'room_id': room['id'],
                    'room_name': room['name'],
                    'balance': 0,
                    'status': 'error',
                    'message': result['message']
                })
        except Exception as e:
            results.append({
                'room_id': room['id'],
                'room_name': room['name'],
                'balance': 0,
                'status': 'error',
                'message': str(e)
            })
    
    return jsonify({
        'status': 'success',
        'count': len(results),
        'rooms': results,
        'timestamp': int(time.time())
    })


@app.route('/api/clear_cache', methods=['POST'])
def clear_cache():
    """清除缓存"""
    cache.clear()
    return jsonify({
        'status': 'success',
        'message': '缓存已清除'
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'message': '接口不存在'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'status': 'error',
        'message': '服务器内部错误'
    }), 500


if __name__ == '__main__':
    # 开发环境运行
    print("=" * 60)
    print("校园水电查询API服务")
    print("=" * 60)
    print("账号/学校代码已从 config.json 读取（已隐藏）")
    # 如需查看，请打开并检查 ESP32_Electric_TTS/config.json（不要提交到 Git 仓库）
    print(f"房间数: {len(CONFIG['rooms'])}")
    print("\n可用接口:")
    print("  GET  /api/rooms          - 获取房间列表")
    print("  GET  /api/query/<id>     - 查询指定房间")
    print("  GET  /api/balance/<id>   - 获取余额（简化）")
    print("  GET  /api/query_all      - 查询所有房间")
    print("  POST /api/clear_cache    - 清除缓存")
    print("\n示例:")
    print("  http://localhost:5000/api/balance/room1")
    print("=" * 60)
    
    # 运行服务器
    app.run(host='0.0.0.0', port=5000, debug=True)
