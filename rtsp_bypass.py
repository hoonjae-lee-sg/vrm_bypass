import asyncio
from datetime import datetime
import re

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"
MY_BRIDGE_IP = "192.168.2.183"

# 카메라 리스트: (이름, 브릿지포트, 실제카메라IP, 카메라포트, 아이디, 비밀번호)
# 비밀번호에 특수문자가 있다면 %23 처럼 인코딩된 형태를 그대로 적으셔도 됩니다.
CAMERAS = [
    ("CH01", 8554, "10.10.1.110", 554, "admin", "SuperGate%23001"),
    # ("CH02", 8555, "10.10.1.111", 554, "admin", "SuperGate%23001"),
    # ... 나머지 13번까지 동일하게 추가
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def inject_auth_and_fix_ip(text, search_addr, camera_addr, user, password):
    """
    주소를 브릿지IP -> 카메라IP로 바꾸면서, 아이디:비밀번호가 없으면 삽입함
    """
    lines = text.splitlines()
    if not lines: return text

    new_lines = []
    for line in lines:
        # rtsp:// 주소가 포함된 라인만 처리
        if "rtsp://" in line:
            # 1. 주소 치환 (192.168.2.183:8554 -> 10.10.1.110:554)
            line = line.replace(search_addr, camera_addr)
            
            # 2. 인증 정보 삽입 (아이디:비번@ 가 없는 경우에만)
            if f"{user}:" not in line and "@" not in line:
                line = line.replace("rtsp://", f"rtsp://{user}:{password}@")
        
        new_lines.append(line)
    
    return "\r\n".join(new_lines) + "\r\n"

async def proxy_task(reader, writer, camera_info, direction):
    """데이터 중계 및 인증/주소 정보 수정"""
    name, b_port, c_ip, c_port, user, pw = camera_info
    bridge_addr = f"{MY_BRIDGE_IP}:{b_port}"
    camera_addr = f"{c_ip}:{c_port}"

    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            # RTSP 제어 패킷(텍스트) 감지
            if data.startswith((b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'RTSP/1.0', b'GET_PARAMETER')):
                try:
                    text = data.decode('utf-8', errors='ignore')
                    
                    if direction == ">>": # 내 PC -> 카메라 (인증 삽입 및 주소 수정)
                        new_text = inject_auth_and_fix_ip(text, bridge_addr, camera_addr, user, pw)
                        print(f"[{get_time()}] [{name}] >> REQ FIXED: {new_text.splitlines()[0]}")
                        data = new_text.encode('utf-8')
                    else: # 카메라 -> 내 PC (주소만 브릿지로 복구)
                        new_text = text.replace(camera_addr, bridge_addr)
                        # 카메라가 보낸 401이나 200 상태 확인을 위한 로그
                        print(f"[{get_time()}] [{name}] << RES: {new_text.splitlines()[0]}")
                        data = new_text.encode('utf-8')
                except Exception as e:
                    print(f"[{get_time()}] [!] [{name}] Error processing text: {e}")

            writer.write(data)
            await writer.drain()
    except:
        pass
    finally:
        writer.close()

async def handle_client(client_reader, client_writer, camera_info):
    name = camera_info[0]
    c_ip = camera_info[2]
    client_info = client_writer.get_extra_info('peername')
    print(f"\n[{get_time()}] [+] [{name}] New Connection from {client_info[0]}")

    try:
        # 실제 카메라와 통신 시작
        remote_reader, remote_writer = await asyncio.open_connection(c_ip, camera_info[3])
        print(f"[{get_time()}] [.] [{name}] Internal Camera Connected ({c_ip})")
        
        await asyncio.gather(
            proxy_task(client_reader, remote_writer, camera_info, ">>"),
            proxy_task(remote_reader, client_writer, camera_info, "<<")
        )
    except Exception as e:
        print(f"[{get_time()}] [-] [{name}] Error: {e}")
    finally:
        print(f"[{get_time()}] [x] [{name}] Connection Closed\n")
        client_writer.close()

async def main():
    print("="*60)
    print(f" RTSP Auth-Injection Proxy (Bridge: {MY_BRIDGE_IP})")
    print("="*60)
    
    servers = []
    for info in CAMERAS:
        # 각 카메라별로 서버 실행
        coro = await asyncio.start_server(
            lambda r, w, i=info: handle_client(r, w, i),
            BRIDGE_IP, info[1]
        )
        print(f"[*] [{info[0]}] Monitoring Port {info[1]} -> {info[2]}")
        servers.append(coro.serve_forever())
    
    await asyncio.gather(*servers)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
