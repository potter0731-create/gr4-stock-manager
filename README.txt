GR4 HDF 재고 감시기
===================

감시 대상
1. 컴퓨존 - RICOH GR IV HDF (GR4 HDF), ProductNo=1353375
2. 유쾌한생각(PLTHINK) - RICOH GR IV GR4 HDF, branduid=1929762

사용법
1. 이 폴더의 install_and_run.bat 를 더블클릭합니다.
2. 처음 실행 시 requests / beautifulsoup4 / winotify 패키지를 설치합니다.
3. 이후에는 run.bat 만 실행해도 됩니다.
4. 검은 창이 떠 있는 동안 약 60초마다 두 사이트를 확인합니다.
5. 재고를 감지하면:
   - 경고음
   - Windows 알림
   - 해당 상품 페이지 자동 열기
   가 실행됩니다.
6. 종료하려면 Ctrl+C 또는 창을 닫습니다.

중요한 감지 방식
- 유쾌한생각은 품절 상태에서도 HTML에 '구매하기'가 남아 있을 수 있으므로
  '품절/SOLD OUT' 신호가 있으면 무조건 품절로 판단합니다.
- 컴퓨존은 '입고 일정이 미정', '재입고 알림 신청', '품절' 등의 신호가 있으면
  품절로 판단합니다.
- 품절 신호가 사라진 상태에서 구매/장바구니 관련 신호까지 확인되어야
  재고 있음으로 판단합니다.
- 네트워크 오류나 사이트 구조가 애매한 경우에는 UNKNOWN으로 처리하고
  재고 알림을 보내지 않습니다.

설정 변경
config.json 을 메모장으로 열어 수정할 수 있습니다.

check_interval_seconds
- 기본 60초
- 너무 짧은 주기는 사이트에 부담이 될 수 있어 프로그램 내부 최소값은 20초입니다.

open_browser_on_stock
- true: 재고 발견 시 상품 페이지 자동 열기
- false: 자동으로 열지 않기

windows_notification / sound_alert
- true/false로 Windows 알림과 소리를 각각 끄고 켤 수 있습니다.

텔레그램 알림(선택)
config.json의 telegram 항목을 아래처럼 설정합니다.

"telegram": {
  "enabled": true,
  "bot_token": "봇 토큰",
  "chat_id": "채팅 ID"
}

로그/상태 파일
- stock_monitor.log : 확인 기록
- stock_state.json  : 이전 재고 상태 저장

주의
- 이 프로그램은 자동 구매/결제를 하지 않습니다. 재고 감지와 알림만 수행합니다.
- 쇼핑몰이 HTML 구조나 품절 문구를 변경하면 감지 규칙도 수정이 필요할 수 있습니다.
