import asyncio
from datetime import datetime
import random

# ==========================================
# 설정 정보
# ==========================================
BRIDGE_IP = "0.0.0.0"
MY_BRIDGE_IP = "192.168.2.183"

CAMERAS = [
    ("CH01", 8554, "10.10.1.101", 554),
    ("CH02", 8555, "10.10.1.102", 554),
    ("CH03", 8556, "10.10.1.103", 554),
    ("CH04", 8557, "10.10.1.104", 554),
    ("CH05", 8558, "10.10.1.105", 554),
    ("CH06", 8559, "10.10.1.106", 554),
    ("CH07", 8560, "10.10.1.107", 554),
    ("CH08", 8561, "10.10.1.108", 554),
    ("CH09", 8562, "10.10.1.109", 554),
    ("CH10", 8563, "10.10.1.110", 554),
    ("CH11", 8564, "10.10.1.111", 554),
    ("CH12", 8565, "10.10.1.112", 554),
    ("CH13", 8566, "10.10.1.113", 554),
    ("CH13", 8567, "10.10.1.114", 554),
    ("CH13", 8568, "10.10.1.115", 554),
    ("CH13", 8569, "10.10.1.116", 554),
    ("CH13", 8570, "10.10.1.117", 554),
    ("CH13", 8571, "10.10.1.118", 554),
    ("CH13", 8572, "10.10.1.119", 554),
]

def get_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def rewrite_rtsp_message(data, b_addr, c_addr, direction):
    RTSP_KEYWORDS = [b'DESCRIBE', b'SETUP', b'PLAY', b'OPTIONS', b'TEARDOWN', b'GET_PARAMETER', b'RTSP/1.0', b'ANNOUNCE', b'RECORD']

    # 패킷이 RTSP 키워드로 시작하는지 엄격하게 검사
    if not any(data.startswith(k) for k in RTSP_KEYWORDS):
        return data  # RTSP 텍스트가 아니면 원본 데이터 반환
    
    try:
        header_end = data.find(b'\r\n\r\n')
        header_part = data[:header_end + 4] if header_end != -1 else data
        body_part = data[header_end + 4:] if header_end != -1 else b''

        text = header_part.decode('utf-8',errors='ignore')
        lines = text.split('\r\n')
        new_lines = []

        for i, line in enumerate(lines):
            if i == 0:
                if direction == ">>":
                    line = line.replace(b_addr, c_addr)
                else:
                    line = line.replace(c_addr, b_addr)
                new_lines.append(line)
                continue

            if line.lower().startswith("authorization:"):
                new_lines.append(line)  # 인증 정보는 그대로 유지
                continue

            if direction == ">>":
                line = line.replace(b_addr, c_addr)
            else:
                line = line.replace(c_addr, b_addr)
            new_lines.append(line)

        final_text = '\r\n'.join(new_lines)
        return final_text.encode('utf-8') + body_part
    except Exception as e:
        return data  # 오류 발생 시 원본 데이터 반환
async def proxy_engine(reader, writer, b_addr, c_addr, name ,conn_id, direction):
    """RTSP/RTP 프로토콜을 바이트 단위로 분석하여 바이너리 오염을 원천 차단"""
    try:
        while not reader.at_eof():
            first_byte = await reader.readexactly(1)
            if not first_byte:
                break
            # 첫 바이트에 따라 처리 로직 추가
            if first_byte == b'$':
                header = await reader.readexactly(3)  # RTP/RTCP 헤더
                length = int.from_bytes(header[1:], byteorder='big')
                payload = await reader.readexactly(length)

                writer.write(b'$' + header + payload)

            else:
                header_chunk = first_byte + await reader.readuntil(b'\r\n\r\n')  # RTSP 헤더

                content_length = 0
                for line in header_chunk.split(b'\r\n'):
                    if line.lower().startswith(b'content-length:'):
                        content_length = int(line.split(b':')[1].strip())
                        break
                full_message = header_chunk
                if content_length > 0:
                    body = await reader.readexactly(content_length)
                    full_message += body
                modified_msg = rewrite_rtsp_message(full_message,b_addr,c_addr, direction)
                writer.write(modified_msg)

            await writer.drain()
    except asyncio.IncompleteReadError:
        pass
    except Exception as e:
        print(f"[{get_time()}] [!] [{name}-{conn_id}] Proxy Error: {e}")
    finally:
        writer.close()


async def handle_client(client_reader, client_writer, camera_info):
    name, b_port, c_ip, c_port = camera_info
    conn_id = random.randint(1000, 9999)
    print(f"[{get_time()}] [*] [{name}-{conn_id}] New Connection from {client_writer.get_extra_info('peername')}")
    b_addr = f"{MY_BRIDGE_IP}:{b_port}"
    c_addr = f"{c_ip}:{c_port}"

    try:
        remote_reader, remote_writer = await asyncio.open_connection(c_ip, c_port)
        await asyncio.gather(
            proxy_engine(client_reader, remote_writer, b_addr, c_addr, name, conn_id, ">>"),
            proxy_engine(remote_reader, client_writer, b_addr, c_addr, name, conn_id, "<<")
        )
    except: pass
    finally: client_writer.close()

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
