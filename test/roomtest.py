"""
방장 위임/삭제 로직을 집중적으로 검증하는 간단한 테스트 스크립트.

사전 조건:
- npchat_server.py가 127.0.0.1:5003에서 실행 중이어야 함.

시나리오:
1) owner가 방 생성, member1/2 입장.
2) owner가 /delete → 남은 멤버 중 랜덤 1명이 방장 승계, owner는 방 밖으로 나감.
3) 새 방장이 아닌 멤버가 /leave → 방에 새 방장만 남게 함.
4) 새 방장이 /delete → 방 삭제 완료.
5) 이후 모두 방 메시지 시도 → NOT_IN_ROOM 에러 기대.
"""

import random
import socket
import time

HOST = "127.0.0.1"
PORT = 5005
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


def parse_new_owner(logs):
    """
    SYSTEM|INFO|owner 님이 방장을 target 님에게 넘기고 방에서 나갔지만 방은 유지됩니다.
    형식에서 target을 추출한다.
    """
    for line in logs:
        if "방장을 " in line and " 님에게 넘기고" in line:
            start = line.find("방장을 ") + len("방장을 ")
            end = line.find(" 님에게 넘기고")
            if start != -1 and end != -1:
                return line[start:end]
    return None


def main():
    room = f"room_{int(time.time())}"
    owner = socket.create_connection((HOST, PORT))
    m1 = socket.create_connection((HOST, PORT))
    m2 = socket.create_connection((HOST, PORT))
    logs = {"owner": [], "m1": [], "m2": []}

    def collect():
        logs["owner"].extend(recv_all(owner))
        logs["m1"].extend(recv_all(m1))
        logs["m2"].extend(recv_all(m2))

    try:
        # 닉 설정
        send(owner, "0|NICK|owner")
        send(m1, "0|NICK|m1")
        send(m2, "0|NICK|m2")
        time.sleep(0.2)
        collect()

        # 방 생성/입장
        send(owner, f"0|CREATE_ROOM|{room}")
        send(m1, f"0|JOIN|{room}")
        send(m2, f"0|JOIN|{room}")
        time.sleep(0.3)
        collect()

        # 원래 방장이 삭제 시도 → 위임 발생
        send(owner, "0|DELETE_ROOM")
        time.sleep(0.3)
        collect()

        # 새 방장 파악 (m1/m2 로그 중 SYSTEM 메시지에서 추출)
        new_owner_nick = parse_new_owner(logs["m1"] + logs["m2"])
        if new_owner_nick is None:
            raise AssertionError("새 방장 닉 추출 실패 (SYSTEM 메시지 없음)")
        if new_owner_nick not in ("m1", "m2"):
            raise AssertionError(f"예상하지 못한 새 방장: {new_owner_nick}")
        new_owner_sock = m1 if new_owner_nick == "m1" else m2
        other_sock = m2 if new_owner_sock is m1 else m1
        other_name = "m2" if new_owner_nick == "m1" else "m1"

        # 새 방장이 아닌 사람은 방을 떠남
        send(other_sock, "0|LEAVE")
        time.sleep(0.2)
        collect()

        # 새 방장이 방을 삭제 (혼자일 때 삭제 가능)
        send(new_owner_sock, "0|DELETE_ROOM")
        time.sleep(0.3)
        collect()

        # 모두 방 메시지 시도 → NOT_IN_ROOM 기대
        send(owner, "1|ROOM_MSG|after_delete_from_owner")
        send(m1, "1|ROOM_MSG|after_delete_from_m1")
        send(m2, "1|ROOM_MSG|after_delete_from_m2")
        time.sleep(0.3)
        collect()

        # 검증
        expect(logs["owner"], "NICK_OK|owner", "owner nick ok")
        expect(logs["m1"], "NICK_OK|m1", "m1 nick ok")
        expect(logs["m2"], "NICK_OK|m2", "m2 nick ok")
        expect(logs["owner"], f"CREATE_ROOM_OK|{room}", "owner create ok")
        expect(logs["m1"], f"JOIN_OK|{room}", "m1 join ok")
        expect(logs["m2"], f"JOIN_OK|{room}", "m2 join ok")
        expect(logs["owner"], f"LEAVE_OK|{room}", "owner leave ok after transfer")
        expect(logs["m1"] + logs["m2"], new_owner_nick, "system message with new owner nick")
        expect(logs[other_name], f"LEAVE_OK|{room}", f"{other_name} leave ok")
        expect(logs["m1"] + logs["m2"], f"DELETE_ROOM_OK|{room}", "final delete ok")
        expect(logs["owner"], "ERROR|NOT_IN_ROOM", "owner msg after delete")
        expect(logs["m1"], "ERROR|NOT_IN_ROOM", "m1 msg after delete")
        expect(logs["m2"], "ERROR|NOT_IN_ROOM", "m2 msg after delete")

        print("=== owner logs ===")
        for line in logs["owner"]:
            print(line)
        print("=== m1 logs ===")
        for line in logs["m1"]:
            print(line)
        print("=== m2 logs ===")
        for line in logs["m2"]:
            print(line)
        print("\nroomtest passed.")
    finally:
        owner.close()
        m1.close()
        m2.close()


if __name__ == "__main__":
    main()
