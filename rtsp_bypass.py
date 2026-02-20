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
    """
    RTSP 제어 메시지(텍스트)만 안전하게 치환. 
    바이너리 데이터가 섞여 있어도 헤더 부분만 정밀 타격함.
    """
    # Interleaved RTP 패킷($로 시작)은 절대 건드리지 않음
    if data.startswith(b'$'):
        return data

    try:
        # RTSP 메시지는 항상 \r\n\r\n으로 헤더가 끝남
        header_end = data.find(b"\r\n\r\n")
        if header_end == -1:
            # 헤더가 한 패킷에 다 안 들어온 경우 전체를 텍스트로 시도
            header_part = data
            body_part = b""
        else:
            header_part = data[:header_end + 4]
            body_part = data[header_end + 4:]

        text = header_part.decode('utf-8', errors='ignore')
        lines = text.split("\r\n")
        
        if not lines or not lines[0]:
            return data

        is_request = any(lines[0].startswith(v) for v in ['DESCRIBE', 'SETUP', 'PLAY', 'OPTIONS', 'TEARDOWN', 'GET_PARAMETER'])
        is_response = lines[0].startswith('RTSP/1.0')

        if is_request or is_response:
            if direction == ">>": # 내 PC -> 카메라
                # 첫 줄 URI 치환 (454 에러 방지)
                if b_addr in lines[0]:
                    old = lines[0]
                    lines[0] = lines[0].replace(b_addr, c_addr)
                    print(f"[{get_time()}] [{name}-{conn_id}] >> [FIXED] {lines[0]}")
                # Auth 헤더는 보존 (로그만 출력)
                for line in lines:
                    if line.lower().startswith("authorization:"):
                        print(f"[{get_time()}] [{name}-{conn_id}] >> [AUTH] {line.strip()}")
            else: # 카메라 -> 내 PC
                print(f"[{get_time()}] [{name}-{conn_id}] << [RES] {lines[0]}")
                # 응답 내 모든 카메라 주소를 브릿지 주소로 복구
                text = "\r\n".join(lines).replace(c_addr, b_addr)
                header_part = text.encode('utf-8')
            
            return header_part + body_part
            
    except Exception as e:
        print(f"[{get_time()}] [!] [{name}-{conn_id}] Error: {e}")
    
    return data

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
