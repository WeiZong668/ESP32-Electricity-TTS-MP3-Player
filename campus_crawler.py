"""
校园水电查询爬虫 - 最终版本
支持查询电费余额、用电记录等信息
"""

import requests
import json
from urllib.parse import unquote


class CampusElectricCrawler:
    """校园水电查询爬虫"""
    
    def __init__(self):
        self.base_url = "https://xqh5.17wanxiao.com"
        self.api_path = "/smartWaterAndElectricityService/SWAEServlet"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; MI 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.99 Mobile Safari/537.36 MicroMessenger/8.0.9',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://xqh5.17wanxiao.com/userwaterelecmini/index.html',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
    
    def query(self, param, customercode, method, command=""):
        """
        查询接口
        
        参数:
            param: JSON字符串或字典，包含查询参数
            customercode: 学校代码
            method: 查询方法
            command: 命令参数
            
        返回:
            dict: 查询结果
        """
        try:
            # 如果param是字典，转换为JSON字符串
            if isinstance(param, dict):
                param = json.dumps(param, ensure_ascii=False)
            
            # 如果param是URL编码的，先解码
            if '%' in param:
                param = unquote(param)
            
            # 构造POST数据
            post_data = {
                'param': param,
                'customercode': customercode,
                'method': method,
                'command': command
            }
            
            # 发送请求
            url = self.base_url + self.api_path
            response = requests.post(
                url,
                headers=self.headers,
                data=post_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # 解析body字段
                if 'body' in result and isinstance(result['body'], str):
                    try:
                        result['body'] = json.loads(result['body'])
                    except:
                        pass
                
                return result
            else:
                return {
                    'success': False,
                    'message': f'HTTP错误: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'请求异常: {str(e)}'
            }
    
    def get_room_info(self, account, customercode, roomverify=None, timestamp=None):
        """
        获取房间信息（包含电费余额）
        
        参数:
            account: 账号（必填）
            customercode: 学校代码（必填）
            roomverify: 房间验证码（可选，不填则查询默认绑定的房间）
            timestamp: 时间戳（可选，默认自动生成）
            
        返回:
            dict: 包含房间信息和电费余额的字典
        """
        import time
        
        if timestamp is None:
            timestamp = str(int(time.time() * 1000))
        
        # 构造查询参数
        param = {
            "cmd": "h5_getstuindexpage",
            "account": account,
            "timestamp": timestamp
        }
        
        # 如果提供了房间验证码，则添加到参数中
        if roomverify:
            param["roomverify"] = roomverify
        
        # 查询
        result = self.query(
            param=param,
            customercode=customercode,
            method="h5_getstuindexpage",
            command="JBSWaterElecService"
        )
        
        # 解析结果
        return self.parse_room_info(result)
    
    def parse_room_info(self, result):
        """
        解析房间信息
        
        返回:
            dict: 格式化后的房间信息
        """
        if not isinstance(result, dict):
            return {'success': False, 'message': '返回数据格式错误'}
        
        # 检查是否查询成功
        if result.get('result_') != 'true':
            return {
                'success': False,
                'message': result.get('message_', '查询失败'),
                'code': result.get('code_', '')
            }
        
        # 提取body数据
        body = result.get('body', {})
        if not isinstance(body, dict):
            return {'success': False, 'message': 'body数据格式错误'}
        
        # 提取关键信息
        info = {
            'success': True,
            'message': body.get('message', '查询成功'),
            'room_number': body.get('roomnum', ''),
            'room_full_name': body.get('roomfullname', ''),
            'room_verify': body.get('roomverify', ''),
        }
        
        # 提取电表信息
        modlist = body.get('modlist', [])
        if modlist and len(modlist) > 0:
            mod = modlist[0]
            info['electric'] = {
                'balance': mod.get('odd', 0),  # 电费余额
                'device_name': mod.get('devicename', ''),
                'device_number': mod.get('blunum', ''),
                'total_purchased': mod.get('sumbuy', 0),  # 总购电量
                'total_subsidy': mod.get('sumsub', 0),  # 总补贴
            }
            
            # 提取每日用电记录
            weekuselist = mod.get('weekuselist', [])
            if weekuselist:
                info['electric']['daily_usage'] = [
                    {
                        'date': item.get('daydate', ''),
                        'weekday': item.get('weekday', ''),
                        'usage': item.get('dayuse', 0)
                    }
                    for item in weekuselist
                ]
            
            # 提取每月用电记录
            monthuselist = mod.get('monthuselist', [])
            if monthuselist:
                info['electric']['monthly_usage'] = [
                    {
                        'year_month': item.get('yearmonth', ''),
                        'usage': item.get('monthuse', 0)
                    }
                    for item in monthuselist
                ]
        
        info['raw_data'] = result
        return info


def query_room_electric(account, customercode, roomverify=None):

    crawler = CampusElectricCrawler()
    return crawler.get_room_info(account, customercode, roomverify)


def print_room_info(info):
    """打印格式化的房间信息"""
    print("\n" + "=" * 60)
    print("查询结果")
    print("=" * 60)
    
    if not info.get('success'):
        print(f"✗ 查询失败: {info.get('message', '未知错误')}")
        return
    
    print(f"✓ 查询成功")
    print(f"\n房间信息:")
    print(f"  房间号: {info.get('room_number', '')}")
    print(f"  房间全称: {info.get('room_full_name', '')}")
    print(f"  房间验证码: {info.get('room_verify', '')}")
    
    if 'electric' in info:
        electric = info['electric']
        print(f"\n电费信息:")
        print(f"  当前余额: {electric.get('balance', 0)} 度")
        print(f"  设备名称: {electric.get('device_name', '')}")
        print(f"  设备编号: {electric.get('device_number', '')}")
        print(f"  总购电量: {electric.get('total_purchased', 0)} 度")
        print(f"  总补贴: {electric.get('total_subsidy', 0)} 度")
        
        # 打印最近用电记录
        if 'daily_usage' in electric and electric['daily_usage']:
            print(f"\n最近用电记录:")
            for record in electric['daily_usage'][-7:]:  # 最近7天
                print(f"  {record['date']} ({record['weekday']}): {record['usage']} 度")
    
    print("=" * 60)


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("校园水电查询爬虫 - 示例")
    print("=" * 60)
    print("此示例已移除真实账号/房间信息。请自行调用 query_room_electric(account, customercode, roomverify) 进行测试。")
    print('示例: query_room_electric(account="YOUR_ACCOUNT", customercode="YOUR_SCHOOL_CODE", roomverify="ROOM_VERIFY_CODE")')
