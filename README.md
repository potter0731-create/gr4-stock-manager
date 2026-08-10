# GR4 HDF 클라우드 재고 감시기

컴퓨터를 켜둘 필요 없이 GitHub Actions가 약 5분 간격으로 아래 두 상품을 확인하고, `품절 → 구매 가능` 전환을 감지하면 Telegram으로 알립니다.

- 컴퓨존: RICOH GR IV HDF (GR4 HDF), ProductNo=1353375
- 유쾌한생각: RICOH GR IV GR4 HDF, branduid=1929762

## 핵심 동작

- GitHub Actions 예약 실행: 약 5분마다 (매시 02, 07, 12, ... 57분 요청)
- 현재 품절 문구와 구매 가능 문구를 함께 검사해 오탐을 줄임
- 컴퓨존 데스크톱 주소가 실패하면 모바일 상품 주소로 한 번 더 확인
- 사이트 응답이 애매하거나 차단된 경우 `unknown`으로 처리하고 기존 상태를 덮어쓰지 않음
- 재고가 계속 있는 동안 반복 알림하지 않고, 품절에서 재고 있음으로 바뀌는 순간에만 알림
- `state.json`은 상태가 실제로 바뀔 때만 갱신됨
- 공개 저장소의 장기 비활성 예약 작업 중단을 피하기 위해 `.monitor-heartbeat`가 월 1회 자동 갱신됨

## 1. Telegram 봇 만들기

1. Telegram에서 `@BotFather`를 엽니다.
2. `/newbot`을 보내고 안내대로 봇 이름과 username을 만듭니다.
3. BotFather가 주는 **bot token**을 복사합니다. 이 토큰은 비밀번호처럼 취급하세요.
4. 방금 만든 봇 채팅을 열고 `/start`를 한 번 보냅니다.

## 2. Telegram chat_id 확인

브라우저에서 아래 주소를 열되 `<BOT_TOKEN>` 부분만 실제 토큰으로 바꿉니다.

```text
https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
```

출력에서 보통 아래와 비슷한 부분이 보입니다.

```json
"chat": {"id": 123456789, ...}
```

그 숫자가 `TELEGRAM_CHAT_ID`입니다.

> 봇에 `/start`를 보낸 뒤 getUpdates를 열어야 chat_id가 잡힙니다.

## 3. GitHub 저장소에 올리기

새 GitHub 저장소를 만든 뒤 이 폴더의 **숨김 폴더 `.github`까지 포함해서** 모든 파일을 업로드합니다.

**5분 감시라면 공개(public) 저장소 사용을 권장합니다.** GitHub 표준 호스티드 러너는 공개 저장소에서 무료/무제한으로 제공됩니다. 비공개(private) 저장소는 계정의 Actions 사용량 한도를 소모하므로 5분 주기에 불리할 수 있습니다. 코드에는 Telegram 토큰을 넣지 않고 GitHub Secrets에만 넣습니다.

## 4. GitHub Secrets 2개 등록

저장소에서:

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

아래 두 개를 만듭니다.

- `TELEGRAM_BOT_TOKEN` = BotFather가 준 토큰
- `TELEGRAM_CHAT_ID` = 위에서 확인한 숫자

**토큰을 코드나 state.json에 직접 적지 마세요.**

## 5. Telegram 연결 테스트

GitHub 저장소의 `Actions` 탭 → `Telegram Test` → `Run workflow`를 누릅니다.

텔레그램으로 아래 메시지가 오면 성공입니다.

`✅ GR4 HDF 재고 감시기 연결 테스트 성공`

## 6. 재고 감시 테스트

`Actions` → `GR4 HDF Stock Monitor` → `Run workflow`를 누르면 즉시 한 번 검사할 수 있습니다.

현재 두 사이트가 품절이면 Telegram 알림은 오지 않는 것이 정상입니다. 대신 Actions 로그에서 각 사이트가 `out_of_stock`으로 판정되는지 확인할 수 있습니다.

그 이후에는 예약 실행이 자동으로 계속됩니다.

## 알림 예시

```text
🚨 GR4 HDF 재고 발견!
판매처: 컴퓨존
상태: 구매 가능 신호 확인
바로가기: https://www.compuzone.co.kr/...
```

## 파일 설명

- `monitor.py` — 두 사이트 확인 + 재고 판정 + Telegram 알림
- `state.json` — 마지막으로 확인된 확실한 재고 상태
- `.github/workflows/stock-monitor.yml` — 약 5분 예약 실행 + 상태/월간 heartbeat 저장
- `.github/workflows/telegram-test.yml` — Telegram 연결 수동 테스트
- `tests/test_monitor.py` — 품절/재고 판정 단위 테스트

## 참고

GitHub Actions의 cron 예약은 정확한 실시간 실행을 보장하지 않습니다. 특히 매시 정각 부근은 지연 가능성이 있어 이 프로젝트는 02, 07, 12 ... 57분으로 오프셋했습니다. GitHub 측 부하 등에 따라 시작이 늦어질 수 있습니다. 사이트가 GitHub 실행 서버의 접속을 차단하거나 HTML 구조를 크게 바꾸면 `unknown`이 뜰 수 있으며, 이 경우 오탐 알림을 보내지 않도록 보수적으로 설계했습니다.
