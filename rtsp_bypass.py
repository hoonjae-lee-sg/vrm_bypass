import asyncio
import re

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"

# 카메라 리스트: (이름, 브릿지포트, 실제카메라IP, 카메라포트)
CAMERAS = [
    ("CH01", 8554, "10.10.1.10", 554),
    ("CH02", 8555, "10.10.1.11", 554),
    ("CH03", 8556, "10.10.1.12", 554),
    # ... 나머지 13번까지 동일한 형식으로 추가하세요
]

async def proxy_engine(reader, writer, src_str, dst_str):
    """
    데이터를 중계하면서 특정 문자열(IP:Port)을 치환함.
    RTP 패킷(PTS 포함)은 건드리지 않고 RTSP 제어문(텍스트)만 수정.
    """
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data:
                break
            
            # RTSP 제어 메시지(텍스트)인 경우에만 치환 수행
            # DESCRIBE, SETUP, PLAY, OPTIONS, RTSP/1.0 등으로 시작하는 경우
            if data[:10].split(b' ')[0] in [b'RTSP/1.0', b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'TEARDOWN']:
                try:
                    # 바이너리 안전을 위해 encode/decode 사용
                    content = data.decode('utf-8', errors='ignore')
                    if src_str in content:
                        content = content.replace(src_str, dst_str)
                        data = content.encode('utf-8')
                except:
                    pass
            
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        if not writer.is_closing():
            writer.close()

async def handle_client(client_reader, client_writer, camera_ip, camera_port):
    """클라이언트와 카메라 간의 연결을 맺고 양방향 치환 프록시 실행"""
    # 내 PC가 접속한 브릿지 PC의 IP와 포트 추출
    local_info = client_writer.get_extra_info('sockname')
    b_ip, b_port = local_info[0], local_info[1]
    
    # 만약 b_ip가 0.0.0.0이면 실제 수신한 인터페이스 IP로 변경 (내 PC가 접속한 IP)
    if b_ip == "0.0.0.0":
        # 클라이언트가 접속한 목적지 IP를 가져옴 (윈도우 환경 대응)
        try:
            b_ip = client_writer.get_extra_info('peername')[0] 
            # 실제로는 client_writer.get_extra_info('sockname')이 맞지만 
            # 일부 환경에서 브릿지 IP를 정확히 알기 위해 192.168 대역 IP를 수동 지정해도 됨
        except:
            pass

    # 치환할 문자열 정의 (예: "192.168.2.183:8554" <-> "10.10.1.10:554")
    bridge_addr = f"{b_ip}:{b_port}"
    camera_addr = f"{camera_ip}:{camera_port}"

    try:
        # 실제 내부망 카메라에 연결
        remote_reader, remote_writer = await asyncio.open_connection(camera_ip, camera_port)
        
        # 1. 내 PC -> 카메라: 브릿지 주소를 카메라 주소로 변경
        c2r = proxy_engine(client_reader, remote_writer, bridge_addr, camera_addr)
        # 2. 카메라 -> 내 PC: 카메라 주소를 브릿지 주소로 변경
        r2c = proxy_engine(remote_reader, client_writer, camera_addr, bridge_addr)
        
        await asyncio.gather(c2r, r2c)
    except Exception as e:
        print(f"[-] 에러 ({camera_ip}): {e}")
    finally:
        client_writer.close()

async def start_proxy(name, local_port, camera_ip, camera_port):
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, camera_ip, camera_port),
        BRIDGE_IP, local_port
    )
    print(f"[*] [{name}] 활성화: {local_port} -> {camera_ip}:{camera_port}")
    async with server:
        await server.serve_forever()

async def main():
    print("=== RTSP Dual-Way Rewrite Proxy ===")
    print("[!] 반드시 RTSP over TCP 모드로 사용하세요.")
    tasks = [start_proxy(*conf) for conf in CAMERAS]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    # 윈도우에서 고성능 비동기 처리를 위해 ProactorEventLoop 사용 (Python 3.8+)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
