import asyncio
import re
from datetime import datetime

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"

# 카메라 리스트 (브릿지 PC에서 내부망 10.10.1.x 카메라로 연결)
CAMERAS = [
    ("CH01", 8554, "10.10.1.10", 554),
    ("CH02", 8555, "10.10.1.11", 554),
    ("CH03", 8556, "10.10.1.12", 554),
    # ... 나머지 채널들 추가
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def rewrite_request(data, b_addr, c_addr, name):
    """클라이언트 -> 카메라: URI 치환"""
    try:
        lines = data.split(b"\r\n")
        if len(lines) > 0 and (b"RTSP" in lines[0]):
            # 로깅: 어떤 요청이 들어왔는지 출력
            print(f"[{get_time()}] [{name}] >> REQ: {lines[0].decode('utf-8', errors='ignore')}")
            
            if b_addr in lines[0]:
                lines[0] = lines[0].replace(b_addr, c_addr)
                return b"\r\n".join(lines)
    except:
        pass
    return data

def rewrite_response(data, c_addr, b_addr, name):
    """카메라 -> 클라이언트: 응답 내 IP 치환"""
    try:
        if data.startswith(b"RTSP/1.0"):
            lines = data.split(b"\r\n")
            print(f"[{get_time()}] [{name}] << RES: {lines[0].decode('utf-8', errors='ignore')}")
            
            decoded = data.decode('utf-8', errors='ignore')
            if c_addr in decoded:
                modified = decoded.replace(c_addr, b_addr)
                return modified.encode('utf-8')
    except:
        pass
    return data

async def pipe_client_to_camera(reader, writer, b_addr, c_addr, name):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            # RTSP 메시지인 경우 로깅 및 치환
            if any(verb in data[:15] for verb in [b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'TEARDOWN']):
                data = rewrite_request(data, b_addr.encode(), c_addr.encode(), name)
            
            writer.write(data)
            await writer.drain()
    except: pass
    finally: writer.close()

async def pipe_camera_to_client(reader, writer, c_addr, b_addr, name):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data: break
            
            if data.startswith(b"RTSP/1.0"):
                data = rewrite_response(data, c_addr, b_addr, name)
            
            writer.write(data)
            await writer.drain()
    except: pass
    finally: writer.close()

async def handle_client(client_reader, client_writer, camera_ip, camera_port, name):
    client_info = client_writer.get_extra_info('peername')
    local_info = client_writer.get_extra_info('sockname')
    
    # 1. 연결 시작 로그
    print(f"[{get_time()}] [+] [{name}] New connection from {client_info[0]}:{client_info[1]}")
    
    b_ip, b_port = local_info[0], local_info[1]
    b_addr = f"{b_ip}:{b_port}"
    c_addr = f"{camera_ip}:{camera_port}"

    try:
        remote_reader, remote_writer = await asyncio.open_connection(camera_ip, camera_port)
        print(f"[{get_time()}] [.] [{name}] Connected to camera {camera_ip}:{camera_port}")
        
        await asyncio.gather(
            pipe_client_to_camera(client_reader, remote_writer, b_addr, c_addr, name),
            pipe_camera_to_client(remote_reader, client_writer, c_addr, b_addr, name)
        )
    except Exception as e:
        print(f"[{get_time()}] [-] [{name}] Error: {e}")
    finally:
        print(f"[{get_time()}] [x] [{name}] Connection closed")
        client_writer.close()

async def start_proxy(name, local_port, camera_ip, camera_port):
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, camera_ip, camera_port, name),
        BRIDGE_IP, local_port
    )
    print(f"[*] [{name}] Listening on {local_port} -> {camera_ip}:{camera_port}")
    async with server:
        await server.serve_forever()

async def main():
    print("=== RTSP Bypass Proxy with Real-time Logging ===")
    tasks = [start_proxy(*conf) for conf in CAMERAS]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
