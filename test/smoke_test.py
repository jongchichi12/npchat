"""
간략한 통합 스모크 테스트 스크립트.

사전 조건: 서버(npchat_server.py)가 127.0.0.1:5002에서 실행 중이어야 합니다.
세 개의 소켓 클라이언트를 띄워 닉 설정 → 방 생성/입장 → 방 메시지/DM/리스트 →
삭제 권한 검증 → 퇴장/삭제 → 재입장 → 종료를 검증합니다.
python ./gimal_server/npchat_server.py 
"""

import socket
import time
import random

HOST = "127.0.0.1"
PORT = 5002
ENCODING = "utf-8"


def send(sock: socket.socket, line: str):
    sock.sendall((line + "\n").encode(ENCODING))


def recv_all(sock: socket.socket, delay: float = 0.1):
    """잠깐 대기하며 수신된 모든 라인을 읽어서 리스트로 반환"""
    sock.setblocking(False)
    lines = []
    end_time = time.time() + delay
    buf = ""
    while time.time() < end_time:
        try:
            data = sock.recv(4096)
            if not data:
                break
            buf += data.decode(ENCODING)
        except BlockingIOError:
            time.sleep(0.01)
    for line in buf.split("\n"):
        line = line.strip()
        if line:
            lines.append(line)
    return lines


def main():
    a = socket.create_connection((HOST, PORT))
    b = socket.create_connection((HOST, PORT))
    c = socket.create_connection((HOST, PORT))  # DM/목록 제약 검증용
    logs = {"a": [], "b": [], "c": []}
    lobby = f"lobby_{int(time.time() * 1000) % 100000}_{random.randint(0, 999)}"
    other = f"other_{int(time.time() * 1000) % 100000}_{random.randint(0, 999)}"

    def collect():
        logs["a"].extend(recv_all(a, 0.2))
        logs["b"].extend(recv_all(b, 0.2))
        logs["c"].extend(recv_all(c, 0.2))

    def expect(log, needle, who):
        if not any(needle in line for line in log):
            raise AssertionError(f"[{who}] '{needle}' not found in {log}")

    try:
        send(a, "0|NICK|aa")
        send(b, "0|NICK|bb")
        send(c, "0|NICK|cc")
        time.sleep(0.2)
        collect()

        # DM 금지: 방에 없는 cc 가 DM 시도 (거부 기대)
        send(c, "1|DM|aa|hi without room")
        time.sleep(0.2)
        collect()

        # 방 생성/입장
        send(a, f"0|CREATE_ROOM|{lobby}")
        send(b, f"0|JOIN|{lobby}")
        time.sleep(0.2)
        collect()

        # 방 메시지/DM
        send(a, "1|ROOM_MSG|hello from aa")
        send(b, "1|DM|aa|hi dm")
        # 방에만 있는인원 검증용
        send(a, "2|LIST_USER")
        # 전체 인원 검증용 방,
        send(a, "2|LIST_ALL")
        time.sleep(0.3)
        collect()

        # 삭제 권한: 비소유자 삭제 실패, 구성원 남아있으면 실패
        send(b, "0|DELETE_ROOM")
        time.sleep(0.2)
        collect()

        send(a, "0|DELETE_ROOM")
        time.sleep(0.2)
        collect()

        # 구성원 퇴장 후 삭제 성공
        send(b, "0|LEAVE")
        time.sleep(0.2)
        collect()

        send(a, "0|DELETE_ROOM")
        time.sleep(0.2)
        collect()

        # 삭제된 방에서 메시지 -> NOT_IN_ROOM
        send(b, "1|ROOM_MSG|after delete")
        time.sleep(0.2)
        collect()

        # 새 방 생성 후 둘 다 입장
        send(a, f"0|CREATE_ROOM|{other}")
        send(b, f"0|JOIN|{other}")
        send(c, f"0|JOIN|{other}")

        # cc가 방 안에서 DM 성공 검증
        send(c, "1|DM|aa|dm after join")
        send(b, "1|ROOM_MSG|welcome to other")
        send(a, "0|QUIT")
        send(b, "0|QUIT")
        send(c, "0|QUIT")

        time.sleep(0.5)
        collect()

        # 기대 검증
        expect(logs["c"], "ERROR|NOT_IN_ROOM", "c DM without room")
        expect(logs["a"], f"CREATE_ROOM_OK|{lobby}", "a create")
        expect(logs["b"], f"JOIN_OK|{lobby}", "b join")
        expect(logs["b"], f"ROOM_MSG|{lobby}|aa|hello from aa", "b recv room msg")
        expect(logs["a"], "DM|bb|hi dm", "a recv dm")
        expect(logs["a"], "USER_LIST", "a list user")
        expect(logs["a"], "USER_LIST_ALL", "a list all")
        expect(logs["b"], "ERROR|INVALID_STATE", "b delete denied")
        expect(logs["a"], "ERROR|INVALID_STATE", "a delete denied while member present")
        expect(logs["b"], f"LEAVE_OK|{lobby}", "b leave ok")
        expect(logs["a"], f"DELETE_ROOM_OK|{lobby}", "a delete ok")
        expect(logs["b"], "ERROR|NOT_IN_ROOM", "b room msg after delete")
        expect(logs["a"], f"CREATE_ROOM_OK|{other}", "a create other")
        expect(logs["b"], f"JOIN_OK|{other}", "b join other")
        expect(logs["c"], f"JOIN_OK|{other}", "c join other")
        expect(logs["c"], "SUCCESS|DM|aa", "c dm success after join ack")
        expect(logs["a"], "DM|cc|dm after join", "a recv dm from c after join")
        expect(logs["b"], f"ROOM_MSG|{other}|bb|welcome to other", "room msg other")

        print("=== client aa recv ===")
        for line in logs["a"]:
            print(line)
        print("=== client bb recv ===")
        for line in logs["b"]:
            print(line)
        print("=== client cc recv ===")
        for line in logs["c"]:
            print(line)
        print("\nAll smoke checks passed.")
    finally:
        a.close()
        b.close()
        c.close()


if __name__ == "__main__":
    main()
