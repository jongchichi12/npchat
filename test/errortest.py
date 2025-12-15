"""
에러 로직을 집중적으로 검증하는 테스트 스크립트.

사전 조건:
- npchat_server.py가 127.0.0.1:5003에서 실행 중이어야 함.

시나리오(에러 기대):
1) 닉 없는 상태에서 JOIN → NEED_NICK
2) 닉 없는 상태에서 LIST_ALL → NEED_NICK
3) 닉 중복 → NICK_IN_USE
4) 방 이름 없는 CREATE_ROOM → INVALID_ROOM_NAME
5) 존재하지 않는 방 JOIN → NO_SUCH_ROOM
6) 방에 없는 상태에서 DELETE_ROOM/LEAVE → NOT_IN_ROOM
7) 방 밖에서 ROOM_MSG → NOT_IN_ROOM
8) 방 밖에서 DM → NOT_IN_ROOM
9) 방 안에서 DM 대상 없음 → NO_SUCH_USER
10) LIST_USER 인자 추가 → BAD_FORMAT
11) LIST_ALL 인자 추가 → BAD_FORMAT
12) 방장 아님 상태에서 DELETE_ROOM → INVALID_STATE
13) UNKNOWN_SUBTYPE / UNKNOWN_TYPE → 에러 반환
"""

import socket
import time

HOST = "127.0.0.1"
PORT = 5004
ENCODING = "utf-8"


def send(sock: socket.socket, line: str):
    sock.sendall((line + "\n").encode(ENCODING))


def recv_all(sock: socket.socket, delay: float = 0.2):
    """delay 동안 논블로킹으로 수신한 모든 줄을 리스트로 반환"""
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


def expect(log, needle, who):
    if not any(needle in line for line in log):
        raise AssertionError(f"[{who}] '{needle}' not found in {log}")


def main():
    # 세 클라이언트 준비
    a = socket.create_connection((HOST, PORT))
    b = socket.create_connection((HOST, PORT))
    c = socket.create_connection((HOST, PORT))
    logs = {"a": [], "b": [], "c": []}
    room = f"room_err_{int(time.time())}"

    def collect():
        logs["a"].extend(recv_all(a))
        logs["b"].extend(recv_all(b))
        logs["c"].extend(recv_all(c))

    try:
        # 1) 닉 없는 상태에서 JOIN/LIST_ALL
        send(c, "0|JOIN|nope")
        send(c, "2|LIST_ALL")
        time.sleep(0.2)
        collect()

        # 닉 설정 (a, b). c는 중복 닉으로 실패 예정
        send(a, "0|NICK|usera")
        send(b, "0|NICK|userb")
        send(c, "0|NICK|usera")  # 중복 닉
        time.sleep(0.2)
        collect()

        # 4) 빈 방 이름으로 CREATE_ROOM (공백만 전달)
        send(a, "0|CREATE_ROOM| ")
        time.sleep(0.2)
        collect()

        # 5) 존재하지 않는 방 JOIN (b)
        send(b, "0|JOIN|no_room")
        time.sleep(0.2)
        collect()

        # a가 정상 방 생성, b가 입장
        send(a, f"0|CREATE_ROOM|{room}")
        send(b, f"0|JOIN|{room}")
        time.sleep(0.3)
        collect()

        # c도 닉은 갖지만 방은 없는 상태로 만들어 이후 NOT_IN_ROOM 시나리오 진행
        send(c, "0|NICK|userc")
        time.sleep(0.2)
        collect()

        # 6) 방에 없는 상태에서 DELETE_ROOM/LEAVE (c는 닉만 있고 방 밖)
        send(c, "0|DELETE_ROOM")
        send(c, "0|LEAVE")
        time.sleep(0.2)
        collect()

        # 7) 방 밖에서 ROOM_MSG / 8) DM
        send(c, "1|ROOM_MSG|hi outside")
        send(c, "1|DM|usera|hi outside dm")
        time.sleep(0.2)
        collect()

        # 9) 방 안에서 DM 대상 없음 (b→nosuch)
        send(b, "1|DM|nosuch|hello")
        time.sleep(0.2)
        collect()

        # 10) LIST_USER 인자 추가 (방 안의 b)
        send(b, "2|LIST_USER|extra")
        time.sleep(0.2)
        collect()

        # 11) LIST_ALL 인자 추가 (등록된 c)
        send(c, "2|LIST_ALL|extra")
        time.sleep(0.2)
        collect()

        # 12) 방장 아님 상태에서 DELETE_ROOM (b 시도)
        send(b, "0|DELETE_ROOM")
        time.sleep(0.2)
        collect()

        # 13) UNKNOWN_SUBTYPE / UNKNOWN_TYPE
        send(a, "0|WHAT|x")
        send(b, "9|NICK|zzz")
        time.sleep(0.2)
        collect()

        # 검증
        expect(logs["c"], "ERROR|NEED_NICK", "c join/listall without nick")
        expect(logs["c"], "ERROR|NICK_IN_USE", "c duplicate nick")
        expect(logs["a"], "ERROR|INVALID_ROOM_NAME", "a create empty room")
        expect(logs["b"], "ERROR|NO_SUCH_ROOM", "b join missing room")
        expect(logs["c"], "ERROR|NOT_IN_ROOM", "c delete/leave outside room")
        expect(logs["c"], "ERROR|NOT_IN_ROOM", "c room msg outside")
        expect(logs["c"], "ERROR|NOT_IN_ROOM", "c dm outside")
        expect(logs["b"], "ERROR|NO_SUCH_USER", "b dm missing user")
        expect(logs["b"], "ERROR|BAD_FORMAT", "b list_user extra arg")
        expect(logs["c"], "ERROR|BAD_FORMAT", "c list_all extra arg")
        expect(logs["b"], "ERROR|INVALID_STATE", "b delete not owner")
        expect(logs["a"], "ERROR|UNKNOWN_SUBTYPE", "a unknown subtype")
        expect(logs["b"], "ERROR|UNKNOWN_TYPE", "b unknown type")

        print("=== logs a ===")
        for line in logs["a"]:
            print(line)
        print("=== logs b ===")
        for line in logs["b"]:
            print(line)
        print("=== logs c ===")
        for line in logs["c"]:
            print(line)
        print("\nerrortest passed.")
    finally:
        a.close()
        b.close()
        c.close()


if __name__ == "__main__":
    main()
