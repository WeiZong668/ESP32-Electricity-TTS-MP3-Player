api_sever是读取宿舍电费主进程
campus_crawler是必须跟api_sever在同目录的文件 16888端口

time_server.py是同步时间,之前ESP 用NTP同步不上 我就自己搭了个 5000端口

simple_tts_server.py是文本转语音,播放声音就是靠他转的  5002端口

记得宝塔放行端口

数据以这个txt为准,其他我叫ai帮我生的readme 可能不准,因为更新过了