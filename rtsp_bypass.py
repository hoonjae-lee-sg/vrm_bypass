import asyncio
from datetime import datetime
import re

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"
MY_BRIDGE_IP = "192.168.2.183"

# 카메라 리스트 (이름, 브릿지포트, 실제카메라IP, 카메라포트)
CAMERAS = [
    ("CH01", 8554, "10.10.1.110", 554),
    ("CH02", 8555, "10.10.1.111", 554),
    ("CH03", 8556, "10.10.1.112", 554),
    # ... 나머지 13번까지 추가하세요
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def log_rtsp_transform(data, search_str, replace_str, name, direction):
    """
    RTSP 패킷 내의 모든 rtsp:// 주소를 찾아 변환하고, 
    [원본 전체 주소] -> [변환된 전체 주소]를 로그로 출력함.
    """
    try:
        text = data.decode('utf-8', errors='ignore')
        lines = text.splitlines()
        modified_lines = []
        is_modified = False

        for line in lines:
            # rtsp:// 주소가 포함된 라인(Request-Line, Content-Base, Authorization 등) 처리
            if "rtsp://" in line and search_str in line:
                old_line = line.strip()
                new_line = line.replace(search_str, replace_str)
                
                # 로그 출력: 원본 주소와 변환된 주소를 모두 표시
                print(f"[{get_time()}] [{name}] {direction} [TRANSFORMED]")
                print(f"  - FROM: {old_line}")
                print(f"  - TO  : {new_line.strip()}")
                
                line = new_line
                is_modified = True
            modified_lines.append(line)

        if is_modified:
            return "\r\n".join(modified_lines).encode('utf-8') + b"\r\n"
    except Exception as e:
        print(f"[{get_time()}] [!] [{name}] Error: {e}")
    
    return data

async def pipe(reader, writer, b_addr, c_addr, name, direction):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            # RTSP 제어 메시지(텍스트)인 경우 주소 변환 및 로그 출력
            if data.startswith((b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'RTSP/1.0', b'GET_PARAMETER', b'ANNOUNCE')):
                if direction == ">>": # 내 PC -> 카메라
                    data = log_rtsp_transform(data, b_addr, c_addr, name, ">>")
                else: # 카메라 -> 내 PC
                    # 응답 코드(200 OK 등)는 무조건 출력
                    try:
                        print(f"[{get_time()}] [{name}] << {data.decode('utf-8', errors='ignore').splitlines()[0]}")
                    except: pass
                    data = log_rtsp_transform(data, c_addr, b_addr, name, "<<")
            
            writer.write(data)
            await writer.drain()
    except: pass
    finally: writer.close()

async def handle_client(client_reader, client_writer, camera_ip, camera_port, name):
    local_info = client_writer.get_extra_info('sockname')
    b_addr = f"{MY_BRIDGE_IP}:{local_info[1]}"
    c_addr = f"{camera_ip}:{camera_port}"

    print(f"\n[{get_time()}] [+] [{name}] Client Connected")

    try:
        remote_reader, remote_writer = await asyncio.open_connection(camera_ip, camera_port)
        print(f"[{get_time()}] [.] [{name}] Camera Connected ({camera_ip})")
        
        await asyncio.gather(
            pipe(client_reader, remote_writer, b_addr, c_addr, name, ">>"),
            pipe(remote_reader, client_writer, b_addr, c_addr, name, "<<")
        )
    except Exception as e:
        print(f"[{get_time()}] [-] [{name}] Error: {e}")
    finally:
        print(f"[{get_time()}] [x] [{name}] Connection Closed\n")
        client_writer.close()

async def main():
    print("="*80)
    print(f" RTSP Verbose Logging Proxy (Bridge: {MY_BRIDGE_IP})")
    print("="*80)
    
    tasks = []
    for name, b_port, c_ip, c_port in CAMERAS:
        server = await asyncio.start_server(
            lambda r, w, ci=c_ip, cp=c_port, n=name: handle_client(r, w, ci, cp, n),
            BRIDGE_IP, b_port
        )
        print(f"[*] [{name}] Listening on {b_port} -> {c_ip}")
        tasks.append(server.serve_forever())
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
