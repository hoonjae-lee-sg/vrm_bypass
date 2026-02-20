import asyncio
from datetime import datetime
import random

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"
MY_BRIDGE_IP = "192.168.2.183"

CAMERAS = [
    ("CH01", 8554, "10.10.1.110", 554),
    ("CH02", 8555, "10.10.1.111", 554),
    # ... 나머지 채널 추가
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def process_rtsp_text(data, b_addr, c_addr, name, conn_id, direction):
    RTSP_KEYWORDS = [b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'TEARDOWN', b'GET_PARAMETER', b'RTSP/1.0', b'ANNOUNCE', b'RECORD']

    # 패킷이 RTSP 키워드로 시작하는지 엄격하게 검사
    if not any(data.startswith(k) for k in RTSP_KEYWORDS):
        return data  # RTSP 텍스트가 아니면 원본 데이터 반환
    
    try:
        # RTSP 헤더와 바디 분리 (헤더 끝은 \r\n\r\n)
        header_end = data.find(b"\r\n\r\n")
        if header_end == -1:
            # 헤더 끝이 없는 경우 (비정상 패킷) - 전체를 헤더로 간주
            header_part = data
            body_part = b""
        else:
            # header_part : RTSP 메시지의 헤더 부분 (텍스트)
            header_part = data[:header_end + 4]
            # body_part : 헤더 끝 이후의 데이터 (RTSP 메시지의 바디, 예: SDP 등)
            body_part = data[header_end + 4:]
            

        # 헤더 부분만 텍스트로 디코딩
        text = header_part.decode('utf-8', errors='ignore')

        # 주소 치환 로직
        if direction == ">>":
            if b_addr in text: # 클라이언트 -> 카메라 방향에서는 브리지 주소를 카메라 주소로 치환
                text = text.replace(b_addr, c_addr)
                # 로그 출력
                first_line = text.split("\r\n")[0]
                print(f"[{get_time()}] [{name}-{conn_id}] >> [FIXED] {first_line}")

        else:
            if c_addr in text: # 카메라 -> 클라이언트 방향에서는 카메라 주소를 브리지 주소로 치환
                text = text.replace(c_addr, b_addr)
                # 로그 출력
                first_line = text.split("\r\n")[0]
                print(f"[{get_time()}] [{name}-{conn_id}] << [RES] {first_line}")
        
        return text.encode('utf-8') + body_part  # 수정된 헤더와 원본 바디를 합쳐서 반환

    except Exception as e:
        print(f"[{get_time()}] [!] [{name}-{conn_id}] RTSP Text Processing Error: {e}")
        return data  # 오류 발생 시 원본 데이터 반환

async def pipe(reader, writer, b_addr, c_addr, name, conn_id, direction):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            # RTSP 텍스트 메시지 가능성이 있는 경우만 처리
            # $ (0x24)로 시작하는 바이너리 데이터는 무조건 통과 (PTS 보존 핵심)
            if not data.startswith(b'$'):
                data = process_rtsp_text(data, b_addr, c_addr, name, conn_id, direction)
            
            writer.write(data)
            await writer.drain()
    except: pass
    finally:
        if not writer.is_closing(): writer.close()

async def handle_client(client_reader, client_writer, camera_info):
    name, b_port, c_ip, c_port = camera_info
    conn_id = random.randint(1000, 9999) # 연결 식별용
    b_addr = f"{MY_BRIDGE_IP}:{b_port}"
    c_addr = f"{c_ip}:{c_port}"

    print(f"\n[{get_time()}] [+] [{name}-{conn_id}] New Connection Started")

    try:
        remote_reader, remote_writer = await asyncio.open_connection(c_ip, c_port)
        print(f"[{get_time()}] [.] [{name}-{conn_id}] Camera Connected: {c_ip}")
        
        await asyncio.gather(
            pipe(client_reader, remote_writer, b_addr, c_addr, name, conn_id, ">>"),
            pipe(remote_reader, client_writer, b_addr, c_addr, name, conn_id, "<<")
        )
    except Exception as e:
        print(f"[{get_time()}] [-] [{name}-{conn_id}] Connection Failed: {e}")
    finally:
        print(f"[{get_time()}] [x] [{name}-{conn_id}] Connection Closed\n")
        client_writer.close()

async def main():
    print("="*80)
    print(f" RTSP Binary-Safe Proxy (PTS/Metadata Fully Preserved) ")
    print("="*80)
    
    tasks = []
    for info in CAMERAS:
        server = await asyncio.start_server(
            lambda r, w, i=info: handle_client(r, w, i),
            BRIDGE_IP, info[1]
        )
        print(f"[*] [{info[0]}] Monitoring Port {info[1]} -> {info[2]}")
        tasks.append(server.serve_forever())
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
