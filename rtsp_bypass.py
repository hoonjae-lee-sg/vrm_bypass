import asyncio
from datetime import datetime

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

def process_client_to_camera(data, name):
    """
    내 PC -> 카메라: 데이터를 변조하지 않고 그대로 전달 (인증/세션 보존)
    """
    try:
        text = data.decode('utf-8', errors='ignore')
        lines = text.split("\r\n")
        if lines and "rtsp://" in lines[0]:
            print(f"[{get_time()}] [{name}] >> [FORWARDING UNTOUCHED]")
            # 요청받은 전체 RTSP 주소와 헤더 정보를 상세히 출력
            for line in lines:
                if "rtsp://" in line or "Authorization" in line:
                    print(f"  - {line.strip()}")
    except:
        pass
    return data

def process_camera_to_client(data, c_addr, b_addr, name):
    """
    카메라 -> 내 PC: 응답 내의 카메라 주소만 브릿지 주소로 치환하여 세션 유지
    """
    try:
        text = data.decode('utf-8', errors='ignore')
        if text.startswith("RTSP/1.0"):
            print(f"[{get_time()}] [{name}] << [RES] {text.splitlines()[0]}")
            
        if c_addr in text:
            new_text = text.replace(c_addr, b_addr)
            # 변환된 주소 로그 출력
            for line in text.splitlines():
                if "rtsp://" in line and c_addr in line:
                    print(f"[{get_time()}] [{name}] << [ADDR REPLACED]")
                    print(f"    FROM: {line.strip()}")
                    print(f"    TO  : {line.replace(c_addr, b_addr).strip()}")
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
                if direction == ">>": # 내 PC -> 카메라 (무변조 통과)
                    data = process_client_to_camera(data, name)
                else: # 카메라 -> 내 PC (주소 치환)
                    data = process_camera_to_client(data, c_addr, b_addr, name)
            
            writer.write(data)
            await writer.drain()
    except: pass
    finally: writer.close()

async def handle_client(client_reader, client_writer, camera_info):
    name, b_port, c_ip, c_port = camera_info
    b_addr = f"{MY_BRIDGE_IP}:{b_port}"
    c_addr = f"{c_ip}:{c_port}"

    print(f"\n[{get_time()}] [+] [{name}] Client Connected")

    try:
        remote_reader, remote_writer = await asyncio.open_connection(c_ip, c_port)
        print(f"[{get_time()}] [.] [{name}] Camera Connected ({c_ip})")
        
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
    print(f" RTSP Transparent Proxy (Session & Auth Fixed) ")
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
