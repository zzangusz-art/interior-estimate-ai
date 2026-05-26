@echo off
chcp 65001 > nul
echo.
echo ====================================
echo  인테리어 견적 AI 분석 서비스 시작
echo ====================================
echo.

if not exist .env (
  echo [경고] .env 파일이 없습니다. .env.example을 복사해서 만들어주세요.
  echo.
  copy .env.example .env
  echo .env 파일이 생성되었습니다. ANTHROPIC_API_KEY를 입력 후 다시 실행하세요.
  pause
  exit /b 1
)

python -m flask run --host=0.0.0.0 --port=5000
pause
