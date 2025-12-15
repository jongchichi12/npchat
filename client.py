# client.py
"""
NP-Chat 프로토콜 클라이언트 예제

사용자 입력 명령어를 프로토콜 메시지로 변환해서 서버에 전송한다.

명령어 예시
-----------
/nick alice          -> 0|NICK|alice
/create study        -> 0|CREATE_ROOM|study
/join lobby          -> 0|JOIN|lobby
/dm bob 안녕         -> 1|DM|bob|안녕
/list                -> 2|LIST_USER
/quit                -> 0|QUIT

서버에서 오는 메시지는 있는 그대로 한 줄씩 출력한다.
"""

import socket
import threading
import sys

HOST = "127.0.0.1"
PORT = 5004
BUF_SIZE = 1024
ENCODING = "utf-8"
# 여기서부터는 클라이언트가 프로토콜 문자열을 만들고, 서버 응답을 읽어 표시하는 로직이다.

def format_server_line(line: str) -> str:
    """서버 메시지를 보기 쉽게 변환 (알 수 없으면 그대로)"""
    parts = line.split("|")
    if not parts:
        return line

    try:
        if parts[0] == "ROOM_MSG" and len(parts) >= 4:
            room, sender, msg = parts[1], parts[2], "|".join(parts[3:])
            return f"[{room}] {sender}: {msg}"
        if parts[0] == "DM" and len(parts) >= 3:
            sender, msg = parts[1], "|".join(parts[2:])
            return f"[DM] {sender}: {msg}"
        if parts[0] == "SYSTEM" and len(parts) >= 3:
            level, msg = parts[1], "|".join(parts[2:])
            return f"[SYSTEM/{level}] {msg}"
        if parts[0] == "USER_LIST" and len(parts) >= 3:
            room, users = parts[1], parts[2]
            return f"[USER_LIST {room}] {users or '(empty)'}"
        if parts[0] == "USER_LIST_ALL" and len(parts) >= 2:
            users = parts[1]
            return f"[USER_LIST_ALL] {users or '(empty)'}"
    except Exception:
        # 파싱 실패 시 원문 반환
        return line

    return line


def update_state_from_server(line: str, state: dict):
    """서버 응답을 보고 닉/방 상태 업데이트"""
    parts = line.split("|")
    if not parts:
        return

    with state["lock"]:
        if parts[0] == "NICK_OK" and len(parts) >= 2:
            state["nick"] = parts[1]
        elif parts[0] in ("CREATE_ROOM_OK", "JOIN_OK") and len(parts) >= 2:
            state["room"] = parts[1]
        elif parts[0] == "DELETE_ROOM_OK":
            state["room"] = None
        elif parts[0] == "LEAVE_OK":
            state["room"] = None
        elif parts[0] == "SYSTEM" and len(parts) >= 3:
            # 방에서 나갔다면 room 상태 초기화
            if "나갔습니다" in parts[2]:
                state["room"] = None
        elif parts[0] == "ERROR":
            # 오류가 나더라도 상태는 그대로 둔다
            pass
        elif parts[0] == "USER_LIST_ALL":
            # 전체 사용자 목록은 상태에 영향 없음
            pass


def recv_loop(sock: socket.socket, state: dict):
    """서버에서 오는 메시지 수신 스레드"""
    buffer = ""
    try:
        while True:
            data = sock.recv(BUF_SIZE)
            if not data:
                print("서버와 연결이 끊어졌습니다.")
                break
            buffer += data.decode(ENCODING)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line:
                    update_state_from_server(line, state)
                    print(f"[SERVER] {format_server_line(line)}")
    except Exception as e:
        print("수신 스레드 에러:", e)
    finally:
        try:
            sock.close()
        except Exception:
            pass
        print("수신 스레드 종료")


def build_protocol_line(cmd: str) -> str | None:
    """
    콘솔에 입력한 문자열을 프로토콜 한 줄로 변환.

    /로 시작하는 건 명령어, 아니면 그냥 ROOM_MSG로 처리한다.
    """
    cmd = cmd.strip()
    if not cmd:
        return None

    # 명령어 파싱 (/로 시작)
    if cmd.startswith("/"):
        # 명령어 키워드만 분리, 나머지는 그대로 둔다 (공백 포함 방 이름/메시지 허용)
        op, *rest = cmd.split(" ", 1)
        op = op.lower()
        tail = rest[0] if rest else ""

        # 접속/방 관리 계열
        if op == "/nick":
            if not tail:
                print("사용법: /nick <이름>")
                return None
            return f"0|NICK|{tail}"

        if op == "/create":
            if not tail:
                print("사용법: /create <방이름>")
                return None
            return f"0|CREATE_ROOM|{tail}"

        if op == "/join":
            if not tail:
                print("사용법: /join <방이름>")
                return None
            return f"0|JOIN|{tail}"

        if op == "/delete":
            return "0|DELETE_ROOM"

        if op == "/quit":
            return "0|QUIT"

        if op == "/leave":
            return "0|LEAVE"

        if op == "/dm":
            to_and_msg = tail.split(" ", 1)
            if len(to_and_msg) < 2:
                print("사용법: /dm <닉네임> <메시지>")
                return None
            to_nick, msg = to_and_msg
            return f"1|DM|{to_nick}|{msg}"

        # 조회 계열 (추가 인자 있으면 그대로 붙여 서버가 형식 오류를 잡도록 전달)
        if op == "/list":
            return f"2|LIST_USER{('|' + tail) if tail else ''}"

        if op == "/listall":
            return f"2|LIST_ALL{('|' + tail) if tail else ''}"

        print("알 수 없는 명령어 혹은 형식 오류입니다.")
        print("사용 가능 명령: /nick, /create, /join, /dm, /list, /listall, /leave, /delete, /quit")
        return None

    # 그냥 일반 텍스트 입력이면 방 메시지로 취급
    return f"1|ROOM_MSG|{cmd}"
    


def build_prompt(state: dict) -> str:
    """현재 닉/방 상태를 프롬프트에 표시"""
    with state["lock"]:
        nick = state.get("nick")
        room = state.get("room")
    # 닉이나 방이 설정되지 않았다면 표시하지 않고 점진적으로 채운다.
    if nick and room:
        return f"[NICK_{nick}/ROOM_{room}] > "
    if nick and not room:
        return f"[NICK_{nick}] > "
    return "> "


def main():
    """TCP 연결을 맺고 입력을 읽어 서버에 전송"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
    except Exception as e:
        print("서버 접속 실패:", e)
        sys.exit(1)

    print(f"서버에 접속했습니다: {HOST}:{PORT}")
    print("명령 예시: /nick 이름, /create 방이름(생성자만 /delete), /join 방이름, /leave, /dm 닉 메시지, /list, /listall, /quit")

    # 상태: 서버 응답으로 채워지는 닉/방, 그리고 스레드 안전을 위한 락
    state = {"nick": None, "room": None, "lock": threading.Lock()}

    t = threading.Thread(target=recv_loop, args=(sock, state), daemon=True)
    t.start()

    try:
        while True:
            try:
                cmd = input(build_prompt(state))
            except EOFError:
                break

            line = build_protocol_line(cmd)
            if line is None:
                continue

            # '\n' 붙여서 전송 (프로토콜 한 줄)
            try:
                sock.sendall((line + "\n").encode(ENCODING))
            except Exception as e:
                print("전송 에러:", e)
                break

            if line.startswith("0|QUIT"):
                break

    except KeyboardInterrupt:
        print("\n사용자 종료")
    finally:
        try:
            sock.close()
        except Exception:
            pass
        print("클라이언트 종료")


if __name__ == "__main__":
    main()
