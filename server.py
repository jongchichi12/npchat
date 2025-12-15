# server.py
"""
NP-Chat 프로토콜 서버 구현 예제
python ./gimal_server/npchat_server.py 

프로토콜 요약
-------------
클라이언트 -> 서버

0|NICK|nick
0|CREATE_ROOM|room
0|JOIN|room
0|QUIT

1|ROOM_MSG|message
1|DM|toNick|message

2|LIST_USER

서버 -> 클라이언트

성공 응답:
NICK_OK|nick
CREATE_ROOM_OK|room
JOIN_OK|room
SUCCESS|DM|toNick
USER_LIST|room|nick1,nick2,...

브로드캐스트:
ROOM_MSG|room|fromNick|message
DM|fromNick|message
SYSTEM|INFO|text

에러:
ERROR|CODE|message
CODE: NEED_NICK, NICK_IN_USE, NOT_IN_ROOM, NO_SUCH_USER,
      ROOM_ALREADY_EXISTS, INVALID_ROOM_NAME, INVALID_STATE,
      UNKNOWN_TYPE, UNKNOWN_SUBTYPE, BAD_FORMAT
"""

import socket
import threading
import random

HOST = ""        # 모든 인터페이스
PORT = 5005
BUF_SIZE = 1024
ENCODING = "utf-8"

# 클라이언트 상태 상수
STATE_CONNECTED = "CONNECTED"
STATE_REGISTERED = "REGISTERED"
STATE_IN_ROOM = "IN_ROOM"
STATE_TERMINATED = "TERMINATED"


class ClientInfo:
    """클라이언트 정보 저장용 클래스"""

    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.nick: str | None = None
        self.state: str = STATE_CONNECTED
        self.room: str | None = None


# 공유 데이터 구조 (접속자/닉/방 매핑을 모두 여기서 관리)
clients_by_sock: dict[socket.socket, ClientInfo] = {}
clients_by_nick: dict[str, ClientInfo] = {}
rooms: dict[str, set[ClientInfo]] = {}
room_owner: dict[str, str] = {}  # room -> owner nick

lock = threading.Lock()


def send_line(sock: socket.socket, text: str):
    """'\n' 붙여서 한 줄 메시지 전송"""
    try:
        sock.sendall((text + "\n").encode(ENCODING))
    except Exception as e:
        print("send_line 에러:", e)


def broadcast_to_room(room: str, text: str, exclude: ClientInfo | None = None):
    """특정 방의 모든 클라이언트에게 메시지 전송 (exclude는 제외)"""
    with lock:
        members = rooms.get(room, set()).copy()
    for c in members:
        if exclude is not None and c.sock is exclude.sock:
            continue
        send_line(c.sock, text)


def send_error(client: ClientInfo, code: str, msg: str):
    send_line(client.sock, f"ERROR|{code}|{msg}")

    """TYPE 0: Control 처리 (닉/방 생성/입장/삭제/퇴장/종료)"""
def handle_control(client: ClientInfo, subtype: str, fields: list[str]):
    
    global clients_by_nick, rooms, room_owner

    if subtype == "NICK":
        # 닉 등록/변경 (중복 닉 방지, 방 소유자 닉 갱신)
        if len(fields) != 1: #닉은 1개의 필드가 필요함
            return send_error(client, "BAD_FORMAT", "NICK requires 1 field")

        nick = fields[0].strip()
        if not nick:
            return send_error(client, "BAD_FORMAT", "Empty nick not allowed")

        old_nick = client.nick
        with lock:
            if nick in clients_by_nick and clients_by_nick[nick].sock is not client.sock:
                # 닉 중복 사용시 에러
                return send_error(client, "NICK_IN_USE", "Nick already in use")

            # 기존 닉 제거
            if client.nick in clients_by_nick:
                del clients_by_nick[client.nick]

            client.nick = nick
            clients_by_nick[nick] = client
            if client.state == STATE_CONNECTED:
                client.state = STATE_REGISTERED
            # 방 소유자 닉 변경 반영
            for room, owner in list(room_owner.items()):
                if owner == old_nick:
                    room_owner[room] = nick
        # 성공 응답
        send_line(client.sock, f"NICK_OK|{nick}")
        print(f"[NICK] {client.addr} -> {nick}")
        return

    if subtype == "CREATE_ROOM":
        # 새 방 생성 후 즉시 입장
        if len(fields) != 1:
            return send_error(client, "BAD_FORMAT", "CREATE_ROOM requires room name")

        room = fields[0].strip()
        if client.state not in (STATE_REGISTERED, STATE_IN_ROOM):
            return send_error(client, "INVALID_STATE", "Need REGISTERED state")

        if not room:
            return send_error(client, "INVALID_ROOM_NAME", "Empty room name")

        with lock:
            if room in rooms:
                return send_error(client, "ROOM_ALREADY_EXISTS", "Room already exists")

            # 새 방 생성
            rooms[room] = set()
            room_owner[room] = client.nick or ""
            # 기존 방에서 제거
            if client.room and client in rooms.get(client.room, set()):
                rooms[client.room].discard(client)
            client.room = room
            client.state = STATE_IN_ROOM
            rooms[room].add(client)

        send_line(client.sock, f"CREATE_ROOM_OK|{room}")
        print(f"[ROOM] {client.nick} created {room}")
        # 방에 들어왔다는 SYSTEM 메시지 브로드캐스트 (나 자신 제외)
        broadcast_to_room(room, f"SYSTEM|INFO|{client.nick} 님이 방을 생성하고 입장했습니다.", exclude=client)
        return

    if subtype == "JOIN":
        # 다른 방으로 이동하거나 입장
        if len(fields) != 1:
            return send_error(client, "BAD_FORMAT", "JOIN requires room name")

        room = fields[0].strip()
        # REGISTERED이거나 이미 다른 방(IN_ROOM)에 있어도 이동 가능
        if client.state not in (STATE_REGISTERED, STATE_IN_ROOM):
            return send_error(client, "INVALID_STATE", "Need REGISTERED state")

        # 이미 같은 방에 있으면 상태 변경/브로드캐스트 없이 즉시 OK 응답
        if client.state == STATE_IN_ROOM and client.room == room:
            return send_line(client.sock, f"JOIN_OK|{room}")

        prev_room = client.room
        with lock:
            if room not in rooms:
                return send_error(client, "NO_SUCH_ROOM", "Room does not exist")

            # 기존 방에서 제거
            if client.room and client in rooms.get(client.room, set()):
                rooms[client.room].discard(client)

            client.room = room
            client.state = STATE_IN_ROOM
            rooms[room].add(client)

        send_line(client.sock, f"JOIN_OK|{room}")
        print(f"[ROOM] {client.nick} joined {room}")
        if prev_room and prev_room != room:
            # 이전 방에 있던 멤버들에게 퇴장 알림
            broadcast_to_room(prev_room, f"SYSTEM|INFO|{client.nick} 님이 방을 나갔습니다.", exclude=client)
        broadcast_to_room(room, f"SYSTEM|INFO|{client.nick} 님이 방에 입장했습니다.", exclude=client)
        return

    if subtype == "DELETE_ROOM":
        # 현재 방을 삭제하고 모든 멤버를 REGISTERED 상태로 돌린다.
        if client.state != STATE_IN_ROOM or client.room is None:
            return send_error(client, "NOT_IN_ROOM", "You must be in a room")

        room = client.room
        transfer_target_nick: str | None = None
        had_members = False
        with lock:
            owner_nick = room_owner.get(room)
            if owner_nick != client.nick:
                return send_error(client, "INVALID_STATE", "Only room creator can delete this room")
            members = list(rooms.get(room, set()))
            others = [c for c in members if c.sock is not client.sock]
            if others:
                # 다른 멤버가 있으면 삭제 대신 방장 권한을 랜덤으로 위임하고, 요청자는 방에서 나간다.
                had_members = True
                target = random.choice(others)
                transfer_target_nick = target.nick or ""
                rooms[room].discard(client)
                client.room = None
                if client.state != STATE_TERMINATED:
                    client.state = STATE_REGISTERED
                room_owner[room] = transfer_target_nick
            else:
                # 남은 인원이 없으면 방 삭제
                if room in rooms:
                    del rooms[room]
                if room in room_owner:
                    del room_owner[room]
                for c in members:
                    c.room = None
                    if c.state != STATE_TERMINATED:
                        c.state = STATE_REGISTERED

        if had_members:
            # 요청자에게 안내하고, 남은 멤버에게 방장 위임 사실 알림
            send_line(client.sock, f"SYSTEM|INFO|방에 다른 인원이 있어 삭제 대신 {transfer_target_nick} 님에게 방장 권한을 넘겼습니다.")
            send_line(client.sock, f"LEAVE_OK|{room}")
            # 남은 멤버에게는 방 유지 + 방장 변경 사실만 알린다 (클라이언트가 방 상태를 유지하도록 '나갔습니다' 문구 피함)
            broadcast_to_room(room, f"SYSTEM|INFO|{client.nick} 님이 방장을 {transfer_target_nick} 님에게 넘기고 방에서 나갔지만 방은 유지됩니다.", exclude=client)
            print(f"[ROOM] {client.nick} transferred ownership of {room} to {transfer_target_nick} and left")
        else:
            # 알림은 락 밖에서 전송
            for c in members:
                if c.sock is client.sock:
                    send_line(c.sock, f"DELETE_ROOM_OK|{room}")
                else:
                    # 다른 멤버도 방이 사라졌음을 알리고 상태 초기화 힌트 제공
                    send_line(c.sock, f"SYSTEM|INFO|{client.nick} 님이 방을 삭제했고 방이 사라져 나갔습니다.")
            print(f"[ROOM] {client.nick} deleted {room}")
        return

    if subtype == "LEAVE":
        # 현재 방에서 나와 REGISTERED 상태로 전환
        if client.state != STATE_IN_ROOM or client.room is None:
            return send_error(client, "NOT_IN_ROOM", "You must be in a room")

        with lock:
            room = client.room
            if room in rooms:
                rooms[room].discard(client)
            # 방장이 나가면 남은 첫 사람에게 소유권 위임, 없으면 제거
            if room_owner.get(room) == client.nick:
                remaining = list(rooms.get(room, set()))
                if remaining:
                    room_owner[room] = remaining[0].nick or ""
                else:
                    room_owner.pop(room, None)
            client.room = None
            client.state = STATE_REGISTERED

        send_line(client.sock, f"LEAVE_OK|{room}")
        broadcast_to_room(room, f"SYSTEM|INFO|{client.nick} 님이 방을 나갔습니다.", exclude=client)
        return

    if subtype == "QUIT":
        # 클라이언트 종료 로직은 handle_client 안에서 공통 처리
        send_line(client.sock, "SYSTEM|INFO|Bye")
        # 이후 실제 정리는 루프 밖에서
        client.state = STATE_TERMINATED
        try:
            client.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        client.sock.close()
        return

    # 알 수 없는 SUBTYPE
    send_error(client, "UNKNOWN_SUBTYPE", f"Unknown control subtype: {subtype}")


def handle_chat(client: ClientInfo, subtype: str, fields: list[str]):
    """TYPE 1: Chat 처리"""
    if client.state != STATE_IN_ROOM:
        return send_error(client, "NOT_IN_ROOM", "You must be in a room")

    if subtype == "ROOM_MSG":
        if len(fields) != 1:
            return send_error(client, "BAD_FORMAT", "ROOM_MSG requires message")

        msg = fields[0]
        room = client.room
        if room is None:
            return send_error(client, "NOT_IN_ROOM", "No room assigned")

        # 방 안 모두에게 브로드캐스트
        broadcast_to_room(room, f"ROOM_MSG|{room}|{client.nick}|{msg}")
        # 굳이 SUCCESS 응답은 생략해도 되지만, 원하면 여기에 추가 가능
        return

    if subtype == "DM":
        if len(fields) != 2:
            return send_error(client, "BAD_FORMAT", "DM requires toNick and message")

        to_nick, msg = fields
        with lock:
            target = clients_by_nick.get(to_nick)

        if target is None:
            return send_error(client, "NO_SUCH_USER", "No such user")

        # DM 전송
        send_line(target.sock, f"DM|{client.nick}|{msg}")
        # 발신자에게도 성공 응답 반환
        send_line(client.sock, f"SUCCESS|DM|{to_nick}")
        return

    send_error(client, "UNKNOWN_SUBTYPE", f"Unknown chat subtype: {subtype}")


def handle_info(client: ClientInfo, subtype: str, fields: list[str]):
    """TYPE 2: Info 처리 (LIST_USER 등)"""
    if subtype == "LIST_USER":
        if fields:
            return send_error(client, "BAD_FORMAT", "LIST_USER takes no args")
        if client.state != STATE_IN_ROOM:
            return send_error(client, "NOT_IN_ROOM", "You must be in a room")

        room = client.room
        with lock:
            members = rooms.get(room, set())
            names = [c.nick for c in members if c.nick is not None]
        users_str = ",".join(names)
        send_line(client.sock, f"USER_LIST|{room}|{users_str}")
        return

    if subtype == "LIST_ALL":
        if fields:
            return send_error(client, "BAD_FORMAT", "LIST_ALL takes no args")
        if client.state not in (STATE_REGISTERED, STATE_IN_ROOM):
            return send_error(client, "NEED_NICK", "Register nick first")
        # 전체 사용자 목록 (REGISTERED/IN_ROOM) 반환
        with lock:
            names = [nick for nick, c in clients_by_nick.items() if c.state in (STATE_REGISTERED, STATE_IN_ROOM)]
        users_str = ",".join(names)
        send_line(client.sock, f"USER_LIST_ALL|{users_str}")
        return

    send_error(client, "UNKNOWN_SUBTYPE", f"Unknown info subtype: {subtype}")


def process_message(client: ClientInfo, line: str):
    """한 줄 메시지 처리: TYPE 파싱 후 각 핸들러로 분배"""
    line = line.strip()
    if not line:
        return

    #구분자로 구분한 문자열이 2개 미만이면 형식이 잘못된거
    parts = line.split("|")
    if len(parts) < 2:
        return send_error(client, "BAD_FORMAT", "Need TYPE and SUBTYPE")

    type_str = parts[0] # 타입 0,1,2 저장하는 곳
    subtype = parts[1] # 서브타입 NICK, CREATE_ROOM 등 저장하는 곳
    fields = parts[2:]  # 나머지

    # TYPE을 파싱해서 타입에 맞는 함수 호출
    try:
        type_num = int(type_str)
    except ValueError:
        return send_error(client, "UNKNOWN_TYPE", f"TYPE must be int: {type_str}")

    # 닉 설정 전에는 NICK 외 명령 차단
    if client.state == STATE_CONNECTED and not (type_num == 0 and subtype == "NICK"):
        return send_error(client, "NEED_NICK", "Set nick first")

    if type_num == 0:
        return handle_control(client, subtype, fields)
    elif type_num == 1:
        return handle_chat(client, subtype, fields)
    elif type_num == 2:
        return handle_info(client, subtype, fields)
    else:
        return send_error(client, "UNKNOWN_TYPE", f"Unknown TYPE: {type_num}")


def cleanup_client(client: ClientInfo):
    """클라이언트 종료 시 정리"""
    room_to_notify = None
    with lock:
        if client.room and client in rooms.get(client.room, set()):
            rooms[client.room].discard(client)
            room_to_notify = client.room
            # 방 소유자가 나가면 남은 첫 사람에게 소유권 위임
            if room_owner.get(client.room) == client.nick:
                members = list(rooms.get(client.room, set()))
                if members:
                    room_owner[client.room] = members[0].nick or ""
                else:
                    room_owner.pop(client.room, None)

        if client.nick in clients_by_nick:
            del clients_by_nick[client.nick]

        if client.sock in clients_by_sock:
            del clients_by_sock[client.sock]

    if room_to_notify:
        # 락을 잡지 않은 상태에서 브로드캐스트 (재진입 데드락 방지)
        broadcast_to_room(room_to_notify, f"SYSTEM|INFO|{client.nick} 님이 방을 나갔습니다.", exclude=client)

    try:
        client.sock.close()
    except Exception:
        pass


def handle_client(sock: socket.socket, addr):
    """각 클라이언트별 스레드 함수"""
    client = ClientInfo(sock, addr)
    with lock:
        clients_by_sock[sock] = client

    print("연결:", addr)

    buffer = ""

    try:
        while client.state != STATE_TERMINATED:
            data = sock.recv(BUF_SIZE)
            if not data:
                break

            buffer += data.decode(ENCODING)
            # '\n' 기준으로 자르기
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                process_message(client, line)

    except Exception as e:
        print("클라이언트 처리 중 에러:", e)

    print("연결 종료:", addr)
    cleanup_client(client)


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(10)
    print(f"서버 대기중... ({HOST or '0.0.0.0'}:{PORT})")

    try:
        while True:
            client_sock, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("서버 종료 요청")
    finally:
        server.close()


if __name__ == "__main__":
    main()
