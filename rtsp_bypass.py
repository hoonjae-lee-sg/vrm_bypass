import asyncio
import re

# ==========================================
# 설정 정보 (브릿지 PC 환경에 맞게 수정하세요)
# ==========================================
BRIDGE_IP = "0.0.0.0" # 모든 네트워크 인터페이스에서 수신

# 카메라 리스트: (이름, 브릿지포트, 카메라IP, 카메라포트)
# 실제 카메라 13개의 IP 주소로 아래 리스트를 채워주세요.
CAMERAS = [
    ("CH01", 8554, "192.168.10.101", 554),
    ("CH02", 8555, "192.168.10.102", 554),
    ("CH03", 8556, "192.168.10.103", 554),
    ("CH04", 8557, "192.168.10.104", 554),
    ("CH05", 8558, "192.168.10.105", 554),
    ("CH06", 8559, "192.168.10.106", 554),
    ("CH07", 8560, "192.168.10.107", 554),
    ("CH08", 8561, "192.168.10.108", 554),
    ("CH09", 8562, "192.168.10.109", 554),
    ("CH10", 8563, "192.168.10.110", 554),
    ("CH11", 8564, "192.168.10.111", 554),
    ("CH12", 8565, "192.168.10.112", 554),
    ("CH13", 8566, "192.168.10.113", 554),
]

# RTSP 헤더 내의 IP/Port 수정을 위한 패턴
IP_PATTERN = re.compile(r"rtsp://(?:\d+\.\d+\.\d+\.\d+)(?::\d+)?")

async def pipe(reader, writer, target_ip=None, target_port=None):
    """두 소켓 간에 데이터를 무결하게 복사 (PTS/Metadata 보존)"""
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data:
                break
            
            # RTSP 제어 메시지(텍스트)인 경우만 주소 수정하여 세션 유지
            if target_ip and data.startswith(b"RTSP"):
                try:
                    decoded = data.decode('utf-8', errors='ignore')
                    new_uri = f"rtsp://{target_ip}:{target_port}"
                    modified = IP_PATTERN.sub(new_uri, decoded)
                    data = modified.encode('utf-8')
                except:
                    pass
            
            # 그 외의 모든 데이터(RTP 패킷 등)는 비트 하나 바꾸지 않고 전송
            writer.write(data)
            await writer.drain()
    except:
        pass
    finally:
        if not writer.is_closing():
            writer.close()

async def handle_client(client_reader, client_writer, camera_ip, camera_port):
    """클라이언트 연결 및 카메라 중계"""
    local_info = client_writer.get_extra_info('sockname')
    local_ip, local_port = local_info[0], local_info[1]
    
    try:
        # 내부망 카메라에 연결 시도
        remote_reader, remote_writer = await asyncio.open_connection(camera_ip, camera_port)
        
        # 양방향 데이터 중계
        await asyncio.gather(
            pipe(client_reader, remote_writer),
            pipe(remote_reader, client_writer, target_ip=local_ip, target_port=local_port)
        )
    except Exception as e:
        print(f"[-] 연결 실패 ({camera_ip}): {e}")
    finally:
        client_writer.close()

async def start_proxy(name, local_port, camera_ip, camera_port):
    """개별 채널 서버 시작"""
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, camera_ip, camera_port),
        BRIDGE_IP, local_port
    )
    print(f"[*] [{name}] Listening on {BRIDGE_IP}:{local_port} -> {camera_ip}:{camera_port}")
    async with server:
        await server.serve_forever()

async def main():
    print("=== RTSP Multi-Channel Bypass Proxy (PTS/Metadata Preserved) ===")
    tasks = [start_proxy(*conf) for conf in CAMERAS]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] 종료 중...")
