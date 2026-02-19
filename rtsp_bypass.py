import asyncio
import re
from datetime import datetime

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"
MY_BRIDGE_IP = "192.168.2.183"

CAMERAS = [
    ("CH01", 8554, "10.10.1.10", 554),
    ("CH02", 8555, "10.10.1.11", 554),
    ("CH03", 8556, "10.10.1.12", 554),
    # ... 13번까지 추가하세요
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def rewrite_rtsp_message(data, target_addr, name, direction):
    """
    RTSP 메시지 내의 모든 주소를 타겟 주소로 치환하며 상세 로그를 남김
    """
    try:
        original = data.decode('utf-8', errors='ignore')
        
        # 정규표현식: rtsp:// + [인증정보@] + [기존주소]
        # 그룹1: rtsp://
        # 그룹2: admin:pass@ (있는 경우)
        pattern = r"(rtsp://)([^@/ ]+@)?[^/ \"']+"
        replacement = r"\1\2" + target_addr
        
        modified = re.sub(pattern, replacement, original)
        
        if original != modified:
            # 첫 번째 줄만 추출하여 비교 로그 생성
            orig_first = original.split('\r\n')[0]
            mod_first = modified.split('\r\n')[0]
            
            print(f"[{get_time()}] [{name}] {direction} [ORIG] {orig_first}")
            print(f"[{get_time()}] [{name}] {direction} [FIXD] {mod_first}")
            
            # 인증 정보가 포함되어 있는지 확인용 로그 (필요시)
            if "@" in mod_first:
                print(f"[{get_time()}] [{name}] {direction} [AUTH] Credentials detected and preserved.")
            
            return modified.encode('utf-8')
    except Exception as e:
        print(f"[{get_time()}] [!] [{name}] Rewrite Error: {e}")
    return data

async def pipe(reader, writer, target_addr, name, direction):
    """데이터 파이프라인 및 RTSP 패킷 감지"""
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            # RTSP 제어 문구 감지 (바이너리 RTP는 건드리지 않음)
            if any(h in data[:15] for h in [b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'RTSP/1.0', b'GET_PARAMETER', b'ANNOUNCE']):
                data = rewrite_rtsp_message(data, target_addr, name, direction)
            
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        if not writer.is_closing():
            writer.close()

async def handle_client(client_reader, client_writer, camera_ip, camera_port, name):
    client_info = client_writer.get_extra_info('peername')
    local_info = client_writer.get_extra_info('sockname')
    
    # 192.168.2.183:8554 형태의 브릿지 주소
    b_ip = local_info[0] if local_info[0] != "0.0.0.0" else MY_BRIDGE_IP
    b_addr = f"{b_ip}:{local_info[1]}"
    
    # 10.10.1.10:554 형태의 카메라 주소
    c_addr = f"{camera_ip}:{camera_port}"

    print(f"\n[{get_time()}] [+] [{name}] New Client Connection: {client_info[0]}:{client_info[1]}")
    print(f"[{get_time()}] [.] [{name}] Mapping: Bridge({b_addr}) <-> Camera({c_addr})")

    try:
        remote_reader, remote_writer = await asyncio.open_connection(camera_ip, camera_port)
        print(f"[{get_time()}] [.] [{name}] Success: Connected to internal camera.")
        
        # 양방향 중계 실행
        # >> : 클라이언트 -> 카메라 (카메라 주소로 변환)
        # << : 카메라 -> 클라이언트 (브릿지 주소로 변환)
        await asyncio.gather(
            pipe(client_reader, remote_writer, c_addr, name, ">>"),
            pipe(remote_reader, client_writer, b_addr, name, "<<")
        )
    except Exception as e:
        print(f"[{get_time()}] [-] [{name}] Connection Failed: {e}")
    finally:
        print(f"[{get_time()}] [x] [{name}] Connection Closed\n")
        client_writer.close()

async def start_proxy(name, local_port, camera_ip, camera_port):
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, camera_ip, camera_port, name),
        BRIDGE_IP, local_port
    )
    print(f"[*] [{name}] Service ready on port {local_port} -> {camera_ip}:{camera_port}")
    async with server:
        await server.serve_forever()

async def main():
    print("="*60)
    print(" RTSP Verbose Debugging Bypass Proxy (Auth & Session Fixed) ")
    print("="*60)
    print(f"[*] Configured Bridge IP: {MY_BRIDGE_IP}")
    tasks = [start_proxy(*conf) for conf in CAMERAS]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        # 윈도우 환경 성능 최적화
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Program terminated by user.")
