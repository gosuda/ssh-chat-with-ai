import paramiko
import time
import random
import string
import socket
from dummy import dummy_data

# SSH 접속 정보
hostname = "localhost"
port = 2222
username = "go양이"

print(f"[DEBUG] SSH 접속 시작: {hostname}:{port}, 사용자: {username}")

# SSH 클라이언트 초기화
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print(f"[DEBUG] 소켓 생성 완료")

sock.connect((hostname, port))
print(f"[DEBUG] 소켓 연결 완료")

transport = paramiko.Transport(sock)
transport.start_client()
print(f"[DEBUG] SSH Transport 시작 완료")

try:
    # "none" 인증 시도
    transport.auth_none(username)
    print(f"[DEBUG] 인증 완료")
    
    # 인터랙티브 셸 열기
    channel = transport.open_session()
    channel.get_pty()
    channel.invoke_shell()
    print(f"[DEBUG] 셸 열기 완료")
    
    idx = 0
    data_len = len(dummy_data)
    print(f"[DEBUG] 무한 루프 시작, 데이터 길이: {data_len}")
    while True:
        idx += 1
        message = dummy_data[(idx - 1) % data_len]
        print(f"[DEBUG] 메시지 전송 ({idx}): {message}")
        channel.send(message + "\r\n")
        print(f"[DEBUG] 10초 대기 중...")
        time.sleep(10)

finally:
    # SSH 연결 종료
    transport.close()
    print(f"[DEBUG] Transport 종료 완료")
    sock.close()
    print(f"[DEBUG] 소켓 종료 완료")

