import asyncio
from datetime import datetime

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"
MY_BRIDGE_IP = "192.168.2.183" # 내 PC가 접속하는 브릿지 PC의 무선 IP

# 카메라 리스트 (이름, 브릿지포트, 실제카메라IP, 카메라포트)
CAMERAS = [
    ("CH01", 8554, "10.10.1.110", 554),
    ("CH02", 8555, "10.10.1.111", 554),
    # ... 13번까지 추가하세요
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

async def proxy_task(reader, writer, b_addr, c_addr, name, direction):
    """
    데이터 중계 및 주소 동적 치환 (인증 정보 보존)
    """
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            # RTSP 제어 패킷(텍스트) 감지
            if data.startswith((b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'RTSP/1.0', b'GET_PARAMETER')):
                try:
                    text = data.decode('utf-8', errors='ignore')
                    
                    if direction == ">>": # 내 PC -> 카메라
                        # 내 PC가 보낸 주소(b_addr)를 카메라 주소(c_addr)로 치환
                        # 이 과정에서 rtsp://admin:pass@ 부분은 전혀 건드리지 않음
                        if b_addr in text:
                            new_text = text.replace(b_addr, c_addr)
                            print(f"[{get_time()}] [{name}] >> REQ: {text.splitlines()[0]}")
                            print(f"[{get_time()}] [{name}] >> FIX: {new_text.splitlines()[0]}")
                            data = new_text.encode('utf-8')
                    
                    else: # 카메라 -> 내 PC
                        # 카메라가 보낸 응답 내의 자기 주소를 다시 브릿지 주소로 복구
                        if c_addr in text:
                            new_text = text.replace(c_addr, b_addr)
                            print(f"[{get_time()}] [{name}] << RES: {new_text.splitlines()[0]}")
                            data = new_text.encode('utf-8')
                            
                except Exception as e:
                    print(f"[{get_time()}] [!] [{name}] Error: {e}")

            writer.write(data)
            await writer.drain()
    except:
        pass
    finally:
        writer.close()

async def handle_client(client_reader, client_writer, camera_ip, camera_port, name):
    client_info = client_writer.get_extra_info('peername')
    local_info = client_writer.get_extra_info('sockname')
    
    # 치환에 사용할 주소 문자열 정의 (IP:PORT)
    # 예: "192.168.2.183:8554" <-> "10.10.1.110:554"
    b_addr = f"{MY_BRIDGE_IP}:{local_info[1]}"
    c_addr = f"{camera_ip}:{camera_port}"

    print(f"\n[{get_time()}] [+] [{name}] New Client: {client_info[0]}:{client_info[1]}")

    try:
        # 실제 카메라와 연결
        remote_reader, remote_writer = await asyncio.open_connection(camera_ip, camera_port)
        print(f"[{get_time()}] [.] [{name}] Camera Connected: {camera_ip}")
        
        # 양방향 중계 시작
        await asyncio.gather(
            proxy_task(client_reader, remote_writer, b_addr, c_addr, name, ">>"),
            proxy_task(remote_reader, client_writer, b_addr, c_addr, name, "<<")
        )
    except Exception as e:
        print(f"[{get_time()}] [-] [{name}] Fail: {e}")
    finally:
        print(f"[{get_time()}] [x] [{name}] Connection Closed\n")
        client_writer.close()

async def main():
    print("="*60)
    print(f" RTSP Dynamic Auth-Preserve Proxy (Bridge: {MY_BRIDGE_IP})")
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
