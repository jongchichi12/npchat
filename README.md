# NP-Chat

TCP 소켓 기반 채팅 서버 / 클라이언트 프로그램  
네트워크 프로그래밍 과제용 프로젝트

- Server: gimal_server/npchat_server.py
- Client: gimal_client/client.py
- Port: 5003
- Encoding: utf-8

---

## 실행 환경
- Python 3.10 이상
- 서버/클라이언트 동일 포트 사용 (5003)
- 같은 PC 테스트 시 127.0.0.1

---

## 저장소 클론

Git이 설치되어 있어야 합니다.

    git clone <repository-url>
    cd <repository-directory>

---

## 실행 방법

### 1. 서버 실행

터미널에서 아래 명령 실행

    cd gimal_server
    python npchat_server.py

아래 메시지가 출력되면 정상 실행

    서버 대기중... (0.0.0.0:5003)

---

### 2. 클라이언트 실행

(여러 명 테스트 시 터미널 여러 개 실행)

    cd gimal_client
    python client.py

- 기본 서버 주소: 127.0.0.1
- 서버가 다른 PC라면 클라이언트 코드에서 서버 IP를 해당 PC IP로 수정

---

## 명령어 사용법

### 닉네임 설정 (필수)

    /nick <닉네임>

- 성공: NICK_OK|닉네임
- 닉네임 중복 불가

---

### 방 생성 / 입장

    /create <방이름>   (방 생성 + 자동 입장, 방장)
    /join <방이름>     (기존 방 입장)

---

### 채팅

슬래시(/) 없이 입력하면 현재 방으로 메시지 전송

    안녕하세요

---

### DM (귓속말)

    /dm <상대닉> <메시지>

---

### 사용자 목록

    /list      현재 방 멤버 목록
    /listall   전체 사용자 목록

---

### 방 나가기 / 삭제

    /leave     방 나가기
    /delete    방 삭제 (방장만 가능)

---

### 종료

    /quit

---

## 로컬 테스트 예시 (2명)

서버 실행

    cd gimal_server
    pythonserver.py

클라이언트 A

    /nick alice
    /create lobby

클라이언트 B

    /nick bob
    /join lobby

---

## 주의사항
- 메시지, 닉네임, 방 이름에 | 문자 사용 금지
- 에러 형식: ERROR|CODE|message
- ERROR|NEED_NICK → /nick 먼저 실행
- ERROR|NOT_IN_ROOM → 방 입장 필요
