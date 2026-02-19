import asyncio
from datetime import datetime

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"
MY_BRIDGE_IP = "192.168.2.183"  # 내 PC에서 접속하는 브릿지 IP

# 실제 카메라 13개의 내부망 IP를 여기에 정확히 적어주세요.
CAMERAS = [
    ("CH01", 8554, "10.10.1.10", 554),
    ("CH02", 8555, "10.10.1.11", 554),
    # ... 필요한 만큼 추가
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

async def proxy_task(reader, writer, search_str, replace_str, name, direction):
    """데이터를 읽어서 주소 치환 후 전달하는 핵심 태스크"""
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            # RTSP 제어 메시지(텍스트)인 경우에만 주소 치환
            if data.startswith((b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'RTSP/1.0', b'GET_PARAMETER')):
                try:
                    # 바이너리 안전을 위해 문자열 치환 후 다시 인코딩
                    text = data.decode('utf-8', errors='ignore')
                    if search_str in text:
                        new_text = text.replace(search_str, replace_str)
                        # 디버깅 로그: 무엇이 어떻게 바뀌었는지 출력
                        print(f"[{get_time()}] [{name}] {direction} {text.splitlines()[0]} -> (FIXED)")
                        data = new_text.encode('utf-8')
                except:
                    pass
            
            writer.write(data)
            await writer.drain()
    except:
        pass
    finally:
        writer.close()

async def handle_client(client_reader, client_writer, camera_ip, camera_port, name):
    """새로운 연결이 들어왔을 때 실행"""
    client_info = client_writer.get_extra_info('peername')
    print(f"[{get_time()}] [+] [{name}] 연결 감지: {client_info[0]}:{client_info[1]}")
    
    # 치환 타겟 설정
    # 내 PC는 192.168.2.183:8554 로 알고 있고, 카메라는 10.10.1.10:554 로 알고 있음
    bridge_addr = f"{MY_BRIDGE_IP}:{client_writer.get_extra_info('sockname')[1]}"
    camera_addr = f"{camera_ip}:{camera_port}"

    try:
        # 카메라로 연결 시도
        remote_reader, remote_writer = await asyncio.open_connection(camera_ip, camera_port)
        print(f"[{get_time()}] [.] [{name}] 카메라 연결 성공 ({camera_ip})")
        
        # 양방향 중계 시작 (치환 포함)
        await asyncio.gather(
            proxy_task(client_reader, remote_writer, bridge_addr, camera_addr, name, ">>"),
            proxy_task(remote_reader, client_writer, camera_addr, bridge_addr, name, "<<")
        )
    except Exception as e:
        print(f"[{get_time()}] [-] [{name}] 연결 실패: {e}")
    finally:
        print(f"[{get_time()}] [x] [{name}] 연결 종료")
        client_writer.close()

async def main():
    print("="*60)
    print(f" RTSP Multi-Channel Bypass Proxy (Bridge IP: {MY_BRIDGE_IP})")
    print("="*60)
    
    servers = []
    for name, local_port, camera_ip, camera_port in CAMERAS:
        coro = await asyncio.start_server(
            lambda r, w, c_ip=camera_ip, c_pt=camera_port, n=name: 
                handle_client(r, w, c_ip, c_pt, n),
            BRIDGE_IP, local_port
        )
        print(f"[*] [{name}] 포트 {local_port} 대기 중... -> {camera_ip}")
        servers.append(coro.serve_forever())
    
    await asyncio.gather(*servers)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
