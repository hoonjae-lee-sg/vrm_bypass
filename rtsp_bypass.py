import asyncio
from datetime import datetime
import re

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"
MY_BRIDGE_IP = "192.168.2.183"

CAMERAS = [
    ("CH01", 8554, "10.10.1.110", 554),
    # ... 나머지 13번까지 추가하세요
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def safe_replace(data, search, replace, name, direction):
    """
    텍스트 내의 모든 검색어(IP:PORT)를 치환하고 로그를 남김
    """
    try:
        text = data.decode('utf-8', errors='ignore')
        if search in text:
            new_text = text.replace(search, replace)
            
            # 로그 출력: 첫 줄 + 인증 헤더 유무 확인
            first_line = text.splitlines()[0] if text.splitlines() else ""
            auth_info = "[AUTH DETECTED]" if "Authorization" in text else "[NO AUTH]"
            print(f"[{get_time()}] [{name}] {direction} {first_line} {auth_info}")
            
            return new_text.encode('utf-8')
    except:
        pass
    return data

async def proxy_task(reader, writer, b_addr, c_addr, name, direction):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            # RTSP 제어 메시지(텍스트) 감지
            if data.startswith((b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'RTSP/1.0', b'GET_PARAMETER', b'ANNOUNCE')):
                if direction == ">>": # 내 PC -> 카메라
                    data = safe_replace(data, b_addr, c_addr, name, ">>")
                else: # 카메라 -> 내 PC
                    # 응답은 내용에 상관없이 항상 로그 출력 (상태 코드 확인용)
                    try:
                        res_line = data.decode('utf-8', errors='ignore').splitlines()[0]
                        print(f"[{get_time()}] [{name}] << {res_line}")
                    except: pass
                    data = safe_replace(data, c_addr, b_addr, name, "<<")
            
            writer.write(data)
            await writer.drain()
    except: pass
    finally: writer.close()

async def handle_client(client_reader, client_writer, camera_ip, camera_port, name):
    client_info = client_writer.get_extra_info('peername')
    local_info = client_writer.get_extra_info('sockname')
    
    # 예: "192.168.2.183:8554", "10.10.1.110:554"
    b_addr = f"{MY_BRIDGE_IP}:{local_info[1]}"
    c_addr = f"{camera_ip}:{camera_port}"

    print(f"\n[{get_time()}] [+] [{name}] Client Connected: {client_info[0]}")

    try:
        remote_reader, remote_writer = await asyncio.open_connection(camera_ip, camera_port)
        print(f"[{get_time()}] [.] [{name}] Camera Connected: {camera_ip}")
        
        await asyncio.gather(
            proxy_task(client_reader, remote_writer, b_addr, c_addr, name, ">>"),
            proxy_task(remote_reader, client_writer, b_addr, c_addr, name, "<<")
        )
    except Exception as e:
        print(f"[{get_time()}] [-] [{name}] Error: {e}")
    finally:
        print(f"[{get_time()}] [x] [{name}] Connection Closed\n")
        client_writer.close()

async def main():
    print("="*60)
    print(f" RTSP Full-Text Replace Proxy (Bridge: {MY_BRIDGE_IP})")
    print("="*60)
    
    tasks = []
    for name, b_port, c_ip, c_port in CAMERAS:
        server = await asyncio.start_server(
            lambda r, w, ci=c_ip, cp=c_port, n=name: handle_client(r, w, ci, cp, n),
            BRIDGE_IP, b_port
        )
        print(f"[*] [{name}] Listening on {b_port} -> {c_ip}:{c_port}")
        tasks.append(server.serve_forever())
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
