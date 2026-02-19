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
    ("CH02", 8555, "10.10.1.111", 554),
    # ... 나머지 13번까지 추가
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def process_client_to_camera(data, b_addr, c_addr, name):
    """
    내 PC -> 카메라: 
    1. 요청 첫 줄(Request-Line)의 주소만 카메라 IP로 치환 (454 에러 방지)
    2. Authorization 헤더의 주소는 그대로 유지 (401 인증 에러 방지)
    """
    try:
        # 바이트 데이터를 문자열로 변환
        text = data.decode('utf-8', errors='ignore')
        lines = text.split("\r\n")
        if not lines or not lines[0]: return data

        # [로그] 클라이언트로부터 받은 원본 데이터 출력
        print(f"[{get_time()}] [{name}] [FROM CLIENT] {lines[0]}")

        # RTSP 메서드 확인 (문자열 비교로 수정)
        verbs = ['DESCRIBE', 'SETUP', 'PLAY', 'OPTIONS', 'TEARDOWN', 'GET_PARAMETER']
        is_request_line = any(lines[0].startswith(verb) for verb in verbs)
        
        if is_request_line:
            # 첫 줄의 브릿지 주소를 카메라 주소로 치환
            if b_addr in lines[0]:
                old_line = lines[0]
                lines[0] = lines[0].replace(b_addr, c_addr)
                print(f"[{get_time()}] [{name}] [TO CAMERA  ] {lines[0]} (IP FIXED)")
            
            # Authorization 헤더 로그 출력 및 보존
            for line in lines:
                if line.lower().startswith("authorization:"):
                    print(f"[{get_time()}] [{name}] [AUTH-INFO ] {line.strip()} (PRESERVED)")
        
        return "\r\n".join(lines).encode('utf-8')
    except Exception as e:
        print(f"[{get_time()}] [!] [{name}] Request Processing Error: {e}")
    return data

def process_camera_to_client(data, c_addr, b_addr, name):
    """
    카메라 -> 내 PC: 응답 내의 모든 카메라 IP를 브릿지 IP로 치환
    """
    try:
        text = data.decode('utf-8', errors='ignore')
        if text.startswith("RTSP/1.0"):
            print(f"[{get_time()}] [{name}] [FROM CAMERA] {text.splitlines()[0]}")
            
        if c_addr in text:
            new_text = text.replace(c_addr, b_addr)
            # 변환된 주소 로그 출력 (Content-Base 등)
            for line in text.splitlines():
                if "rtsp://" in line and c_addr in line:
                    print(f"[{get_time()}] [{name}] [TO CLIENT  ] {line.replace(c_addr, b_addr).strip()}")
            return new_text.encode('utf-8')
    except:
        pass
    return data

async def pipe(reader, writer, b_addr, c_addr, name, direction):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            # RTSP 제어 메시지(텍스트) 감지
            if data.startswith((b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'RTSP/1.0', b'GET_PARAMETER', b'ANNOUNCE')):
                if direction == ">>": # 내 PC -> 카메라
                    data = process_client_to_camera(data, b_addr, c_addr, name)
                else: # 카메라 -> 내 PC
                    data = process_camera_to_client(data, c_addr, b_addr, name)
            
            writer.write(data)
            await writer.drain()
    except: pass
    finally:
        if not writer.is_closing():
            writer.close()

async def handle_client(client_reader, client_writer, camera_info):
    name, b_port, c_ip, c_port = camera_info
    b_addr = f"{MY_BRIDGE_IP}:{b_port}"
    c_addr = f"{c_ip}:{c_port}"

    print(f"\n[{get_time()}] [+] [{name}] Connection Started")

    try:
        remote_reader, remote_writer = await asyncio.open_connection(c_ip, c_port)
        print(f"[{get_time()}] [.] [{name}] Camera Connected: {c_ip}")
        
        await asyncio.gather(
            pipe(client_reader, remote_writer, b_addr, c_addr, name, ">>"),
            pipe(remote_reader, client_writer, b_addr, c_addr, name, "<<")
        )
    except Exception as e:
        print(f"[{get_time()}] [-] [{name}] Fail: {e}")
    finally:
        print(f"[{get_time()}] [x] [{name}] Connection Closed\n")
        client_writer.close()

async def main():
    print("="*80)
    print(f" RTSP Precision Bypass Proxy (Bridge: {MY_BRIDGE_IP})")
    print("="*80)
    
    tasks = []
    for info in CAMERAS:
        server = await asyncio.start_server(
            lambda r, w, i=info: handle_client(r, w, i),
            BRIDGE_IP, info[1]
        )
        print(f"[*] [{info[0]}] Port {info[1]} -> {info[2]}")
        tasks.append(server.serve_forever())
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
