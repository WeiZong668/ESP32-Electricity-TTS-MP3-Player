# ESP32-Electricity-TTS-MP3-Player
ESP32接入完美校园电费播报宿舍电费
通过服务器运行python脚本 获取到完美校园宿舍的电费 然后通过tts文本转语音,再在喇叭中播放出来
如果好用,希望给个⭐,你的支持是我最大的动力,如果有很多人需要,后续会更新,谢谢！

使用:
api_sever是读取宿舍电费主进程
campus_crawler是必须跟api_sever在同目录的文件 16888端口

time_server.py是同步时间,之前ESP 用NTP同步不上 我就自己搭了个 5000端口

simple_tts_server.py是文本转语音,播放声音就是靠他转的  5002端口

记得宝塔放行端口

数据以这个txt为准,其他我叫ai帮我生的readme 可能不准,因为更新过了
