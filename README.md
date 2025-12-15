Getting Started
1) 저장소 클론 (VS Code)
# VS Code에서 터미널 열기 후
git clone <repo-url>
cd <repo-name>
code .
VS Code UI에서 “Clone Repository…”로도 동일하게 클론한 뒤 code .로 워크스페이스를 엽니다.

2) 실행 전 준비
Python 3.10+ (예: 3.13) 설치 확인
포트: 기본 5003 사용 (서버/클라이언트 모두 동일 포트)
3) 서버 실행
python npchat_server.py
콘솔에 서버 대기중... (0.0.0.0:5003)이 보이면 준비 완료.
4) 클라이언트 실행 (터미널 여러 개)
python client.py
기본 접속 대상: 127.0.0.1:5003
여러 명으로 테스트하려면 터미널을 추가로 열어 같은 명령을 실행하세요.
사용법 (명령과 동작)
닉네임 설정

/nick <이름>
성공 시 NICK_OK|이름

방 생성 (생성자가 방장, 즉시 입장)

/create <방이름>
성공 시 CREATE_ROOM_OK|방이름

방 입장

/join <방이름>
성공 시 JOIN_OK|방이름

채팅 (슬래시 없이 입력하면 방 메시지로 전송)

예: 안녕하세요 → [방이름] 닉네임: 안녕하세요
귓속말/DM

/dm <닉네임> <메시지>
성공 시 발신자는 SUCCESS|DM|대상, 수신자는 [DM] 발신자: 메시지

사용자 목록

현재 방 멤버: /list → USER_LIST|방|닉1,닉2,...
전체 등록 사용자: /listall → USER_LIST_ALL|닉1,닉2,...
방 나가기

/leave
성공 시 LEAVE_OK|방

방 삭제

/delete
방장이면 삭제. 방에 다른 멤버가 있으면 랜덤 1명에게 방장 위임 후 방 유지, 요청자는 방에서 나감.
방에 혼자면 삭제되고 모든 멤버(본인 포함)는 방 밖 상태로 초기화.
종료

/quit
클라이언트 종료, 서버 쪽 연결 정리.

실행 순서 예시 (로컬에서 2명 테스트)
터미널 A: python npchat_server.py (서버 실행)
터미널 B: python client.py → /nick alice → /create lobby
터미널 C: python client.py → /nick bob → /join lobby
채팅: 터미널 B에서 안녕 → 터미널 C에 [lobby] alice: 안녕 표시
DM: 터미널 C에서 /dm alice hi → 터미널 B에 [DM] bob: hi
목록: 터미널 B /list → USER_LIST|lobby|alice,bob
방장 위임/삭제: 터미널 B /delete (멤버가 남아 있으면 위임), 또는 멤버 나간 뒤 /delete로 방 삭제
종료: 각각 /quit
기타
메시지/방/닉에 공백 사용 가능 (| 문자는 사용 불가).
에러 응답은 ERROR|CODE|message 형식으로 내려오며, 코드별 설명은 errortype.md 참고.
