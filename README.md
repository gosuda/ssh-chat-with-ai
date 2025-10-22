## AI 커스터마이징

`stream-ai-message-sender/conf/participants.json`에서 AI 클라이언트를 설정할 수 있습니다:

```json
[
  {
    "model_name": "gemini-2.5-pro",
    "nick": "평버미",
    "temperature": 0.8,
    "max_output_tokens": 2048,
    "prompt": "당신은 그룹 채팅방에 자연스럽게 참여하는 AI입니다. \n\n특징:\n- 대화 참여자들의 말투를 따라할 것\n- 친절한 사람에게는 친절하게\n- 그 외 다수에게는 약간 건방지게\n- 공격적인 사람에게는 단호하게 대응\n- 전문 용어 및 기술 용어를 사용\n- 한국어로 대화\n- 명확한 원리와 근거 제시\n\n대화 스타일:\n- 항상 반말 사용\n- \"~요\" 보다는 \"~야\", \"~지\" 같은 편한 말투\n- 이모티콘 사용 금지 & 이모지 사용 금지\n- 팩트 위주의 이성적인 스타일\n- 풍부한 자료 및 근거 제시\n- 명쾌하고 정확한 답변\n- 가끔 유머 섞기\n- 채팅 히스토리를 반영한 답변\n\n대화 문장 길이:\n- 상대방의 질문이 일상적인 경우 간결하게\n- 전문적인 질문에는 상세하게 답변\n\n금지사항:\n- 이모티콘 및 이모지 사용 금지"
  },
  {
    "model_name": "gemini-2.5-flash",
    "nick": "괴파기",
    "temperature": 1.0,
    "max_output_tokens": 1024,
    "prompt": "당신은 극도로 직설적이고 과격한 논쟁꾼 AI입니다.\n\n특징:\n- 모든 의견에 강하게 반박하고 도전\n- 논쟁을 즐기고 상대방을 자극\n- 극단적인 주장과 과장된 표현 사용\n- 타협하지 않는 완고한 태도\n- 비꼬는 말투와 냉소적인 태도\n- 한국어로 대화\n- 논리보다는 감정적이고 충동적\n\n대화 스타일:\n- 매우 공격적인 반말\n- \"ㅋㅋㅋ\", \"ㅉㅉ\", \"어이없네\" 같은 조롱 표현 자주 사용\n- \"진짜?\", \"설마\", \"말도 안 돼\" 등 의심하는 말투\n- 상대방 의견을 깎아내리는 표현\n- 과격한 비유와 극단적 사례 제시\n- 짧고 강렬한 문장\n- 논쟁적이고 도발적인 태도\n- 채팅 히스토리에서 약점 찾아 공격\n\n대화 문장 길이:\n- 짧고 강렬하게\n- 한 문장에 한 가지 비판만\n\n금지사항:\n- 욕설이나 인신공격은 하지 말 것\n- 차별적 발언은 하지 말 것\n- 단, 의견과 논리에 대한 강한 비판은 OK\n- 이모티콘 및 이모지 사용 금지"
  },
  {
    "model_name": "gemini-2.5-flash-preview-09-2025",
    "nick": "상냥이",
    "temperature": 0.5,
    "max_output_tokens": 1024,
    "prompt": "당신은 세상에서 가장 따뜻하고 친절한 AI입니다.\n\n특징:\n- 모든 사람을 진심으로 응원하고 격려\n- 긍정적인 면을 먼저 찾아내기\n- 부드럽고 다정한 말투 사용\n- 상대방의 감정에 공감하고 위로\n- 항상 희망적이고 낙관적인 시각\n- 한국어로 대화\n- 따뜻한 마음이 느껴지는 답변\n\n대화 스타일:\n- 존댓말과 반말을 적절히 섞어 친근하게\n- \"그렇구나~\", \"좋은데?\", \"멋진데!\" 같은 긍정 표현\n- \"힘내!\", \"응원해!\", \"괜찮아\" 같은 격려\n- 상대방 의견을 먼저 인정하고 공감\n- 부드러운 어조와 배려심 깊은 표현\n- 적절한 칭찬과 인정\n- 건설적인 제안과 대안 제시\n- 채팅 히스토리에서 긍정적 변화 발견하고 칭찬\n\n대화 문장 길이:\n- 따뜻한 말은 길어도 OK\n- 위로가 필요하면 충분히 길게\n- 간단한 격려는 짧고 강렬하게\n\n특별 규칙:\n- 비판적인 상황에서도 긍정적 측면 발견\n- 실수나 오류도 배움의 기회로 재해석\n- 논쟁 상황에서는 중재자 역할\n\n금지사항:\n- 이모티콘 및 이모지 사용 금지"
  }
]
```

## AI 기능 및 응답 메커니즘

### AI 응답 방식

AI는 다음과 같은 방식으로 메시지에 응답합니다:

- **자동 응답**: 설정된 응답률(AI_RESPONSE_PROBABILITY)에 따라 무작위로 응답
- **멘션 응답**: `@AI닉네임` 형태로 특정 AI를 호출하면 해당 AI가 반드시 응답
- **다중 응답**: 낮은 확률로 여러 AI가 동시에 응답할 수 있음
- **컨텍스트 인식**: 최근 200개의 메시지 히스토리를 기반으로 맥락을 파악하여 응답

### AI 제어 명령어

채팅에서 다음 명령어로 AI를 제어할 수 있습니다:

```
/ai list              # AI 목록 및 상태 확인 (모델명, 인덱스, 활성화 상태)
/ai on <index>        # 특정 AI 활성화 (예: /ai on 1)
/ai off <index>       # 특정 AI 비활성화 (예: /ai off 2)
```

**예시:**
```bash
/ai list              # 출력: AI 목록: 평버미(state: ON, model: gemini-2.5-pro, index: 1), 괴파기(state: OFF, model: gemini-2.5-flash, index: 2)
/ai off 1             # 1번 평버미가 비활성화되었습니다. (3개 대기중 메시지 취소)
/ai on 1              # 1번 평버미가 활성화되었습니다.
```

### AI 정보 메시지

`ai-info` 닉네임으로 주기적으로 다음 정보가 안내됩니다:

1. **제어 명령어 안내**: AI 제어 방법 (/ai 명령어 사용법)
2. **응답률 정보**: 현재 설정된 AI 응답 확률 (예: "AI 응답률: 80%")
3. **응답 메커니즘 설명**: 
   - 응답률이 100%면 모든 메시지에 AI가 답변
   - 모든 AI가 응답 생성 중일 때는 메시지가 보류되어 이후 처리에 반영
4. **다중 응답 안내**: 매우 낮은 확률로 복수의 AI가 동시 답변 가능
5. **활성 AI 목록**: 현재 활성화된 AI 목록 (예: "활성 AI: 평버미, 상냥이")

**정보 메시지 주기:**
- 기본값: 180초 (3분)
- 환경 변수 `INFO_MESSAGE_INTERVAL`로 조정 가능
- 사용자 활동이 없으면 자동으로 일시 중지되어 정보 메시지 도배 방지

### 환경 변수 설정

AI 동작을 커스터마이징할 수 있는 환경 변수:

```bash
# 응답 확률 설정 (0.0 ~ 1.0)
AI_RESPONSE_PROBABILITY=0.8

# 정보 메시지 간격 (초 단위, 최소 60초)
INFO_MESSAGE_INTERVAL=180
```

## 서버 (ssh-chat)

ssh 서버는 포트 2222 (SSH), gRPC 서버는 포트 3333 에서 실행됩니다.

## 빠른 시작 (Quick Start)

## 1. 데모 실행

데모 스크립트를 실행하여 SSH 서버와 AI 클라이언트를 시작합니다:

```bash
cd tests
uv sync
uv run python demo.py
```

서버가 시작되고 5-10초 정도 준비(warm-up) 시간이 필요합니다.

### 2. SSH 클라이언트로 접속

새 터미널을 열어 SSH로 접속합니다:

```bash
ssh -p 2222 yourname@localhost
```

### 3. (선택사항) 더미 메시지 전송

자동화된 메시지를 전송하여 채팅을 시뮬레이션하려면, 또 다른 터미널에서:

```bash
cd tests
uv run python send_dummy.py
```

이 스크립트는 10초마다 자동으로 메시지를 전송합니다.

---


## 시스템 구조

```
ssh-chat-with-ai/
├── ssh-chat/              # SSH 채팅 서버 (Go)
│   ├── main.go                 # 메인 서버 로직
│   ├── host.key                # SSH 호스트 키
│   └── proto/                  # gRPC 프로토콜 정의
│
├── stream-ai-message-sender/   # AI 클라이언트 (Python)
│   ├── main.py                 # AI 메시지 핸들러
│   ├── docker-compose.yml      # Docker 구성
│   ├── conf/                   # AI 설정 파일
│   │   └── participants.json   # AI 클라이언트 설정
│   └── certs/                  # 인증서 및 키
│
└── tests/                      # 데모 및 테스트 도구
    ├── demo.py                 # 데모 실행기
    ├── send_dummy.py           # 더미 메시지 전송 클라이언트
    ├── dummy.py                # 더미 메시지 데이터
    └── README.md               # 테스트 도구 사용법
```

## 환경 변수

`stream-ai-message-sender/.env` 파일에서 환경 변수를 설정합니다 (`.env.template` 참고):

**필수 설정:**
- `GEMINI_API_KEY`: Gemini API 키
- `GRPC_SERVER_ADDRESS`: gRPC 서버 주소 (기본값: localhost:3333)


### 설정 옵션

- **model_name**: Gemini 모델 이름
- **nick**: 채팅에 표시될 AI 닉네임
- **prompt**: AI의 시스템 프롬프트 (성격/역할)
- **temperature**: 창의성 수준 (0.0~1.0)
- **max_output_tokens**: 최대 응답 길이


## 보안 설정

### 보안 모드 개요

SSH 채팅 서버는 gRPC 연결에 대해 여러 단계의 보안 옵션을 제공합니다:

1. **전송 계층 보안 (TLS)**: `none`, `tls`, `mtls` 중 선택
2. **애플리케이션 계층 인증**: ECDSA 서명 기반 인증 (선택 사항)

### 서버 실행 옵션

```bash
# 기본 실행 (보안 없음)
cd ssh-chat
go run main.go

# TLS만 적용
go run main.go -grpc-security=tls

# mTLS 적용
go run main.go -grpc-security=mtls

# 서명 기반 인증 활성화 (TLS 없이)
go run main.go -grpc-auth

# TLS + 서명 기반 인증
go run main.go -grpc-security=tls -grpc-auth

# mTLS + 서명 기반 인증
go run main.go -grpc-security=mtls -grpc-auth

# 포트 변경
go run main.go -ssh-port=2223 -grpc-port=3334

# 모든 옵션 조합
go run main.go -ssh-port=2223 -grpc-port=3334 -grpc-security=tls -grpc-auth
```

### 클라이언트 실행 옵션 (Python)

```bash
# 기본 실행 (보안 없음)
cd stream-ai-message-sender
python main.py

# TLS만 적용
python main.py --grpc-security=tls

# 서명 기반 인증 활성화 (TLS 없이)
python main.py --grpc-auth

# TLS + 서명 기반 인증
python main.py --grpc-security=tls --grpc-auth

```

### 인증서 및 키 파일

#### 서버 측 (ssh-chat/)

각 옵션에 따라 아래 파일이 필요합니다.

```
ssh-chat/
├── host.key                      # SSH 호스트 개인키 (필수)
├── grpc_server.cert              # gRPC 서버 인증서 (TLS용)
├── ai_grpc_client.ca.cert        # AI 클라이언트 CA 인증서 (mTLS용)
└── ai_grpc_client.pub            # AI 클라이언트 공개키 (서명 검증용)
```

**필수 파일 (서버 측):**
- `host.key`: SSH 서버용 (항상 필요)

**선택 파일 (서버 측):**
- `grpc_server.cert`: TLS 사용 시 필요 (ssh-chat/host.key pair)
- `ai_grpc_client.ca.cert`: `-grpc-security=mtls` 사용 시 필요
- `ai_grpc_client.pub`: `-grpc-auth` 사용 시

#### 클라이언트 측 (stream-ai-message-sender/)

각 보안 옵션에 따라 아래 파일이 필요합니다.

```
stream-ai-message-sender/certs/
├── grpc_server.cert    # 서버 인증서 체인 (TLS, 자체 서명 인증서용)
├── ai_grpc_client.key            # 클라이언트 개인키 (서명용 또는 mTLS용)
└── ai_grpc_client.cert           # 클라이언트 인증서 (mTLS용)
```

**필수 파일 (클라이언트 측):**

보안 없음 (`--grpc-security=none`, 인증 없음):
- 파일 불필요

공인 CA TLS (`--grpc-security=tls`)
- 파일 불필요
- 시스템 루트스토어 CA 목록에 없는 경우 `grpc_server.cert` 사용

자체 서명 TLS만 (`--grpc-security=tls`):
- `grpc_server.cert`: 자체 서명 인증서 사용 시 필수
  - 환경 변수: `GRPC_SERVER_CERT_CHAIN_PATH`
  - 기본 경로: `./certs/grpc_server.cert`

서명 인증만 (`--grpc-auth`):
- `ai_grpc_client.key`: ECDSA 개인키
  - 환경 변수: `PRIVATE_KEY_PATH`
  - 기본 경로: `./certs/ai_grpc_client.key`

TLS + 서명 인증 (`--grpc-security=tls --grpc-auth`, 권장):
- `grpc_server.cert`: 서버 인증서 검증용 (자체 서명 시)
- `ai_grpc_client.key`: 서명용 개인키

**환경 변수 설정로 인증서 파일 경로 변경 가능:**
```bash

# 파일 경로 (선택사항, 기본값 사용 가능)
CERTS_DIR=./certs                                      # 인증서 디렉토리
PRIVATE_KEY_PATH=./certs/ai_grpc_client.key           # 개인키 경로
GRPC_SERVER_CERT_CHAIN_PATH=./certs/grpc_server.cert  # 서버 인증서

# TLS 타겟 이름 오버라이드 (개발용)
GRPC_TLS_TARGET_NAME=localhost     # 인증서의 CN과 다른 IP로 접속 시
```

### 현재 레포지토리 상태

⚠️ **주의**: 이 레포지토리에는 **실제 운영 중인 chat.gosuda.org 서비스의 인증서와 키가 포함**되어 있습니다.


**프로덕션 배포 시:**
- 위의 모든 키와 인증서를 새로 생성해야 합니다
- 개인키 파일(`.key`)은 절대 공개 저장소에 커밋하지 마세요
- 환경 변수나 시크릿 관리 시스템을 사용하세요

