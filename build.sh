#!/bin/bash

terminate() {
    echo "모든 프로세스를 종료 중입니다..."
    # trap을 비활성화하여 무한 루프 방지
    trap - EXIT SIGINT SIGTERM
    # 현재 프로세스 그룹의 모든 자식 프로세스 종료
    kill $(jobs -p) 2>/dev/null
    exit 0
}

trap terminate EXIT SIGINT SIGTERM

echo "React 빌드 중..."
cd ui && npm install && npm run build
# vite.config.js의 outDir 설정으로 server/static/ 에 자동 복사됨

echo "서버 실행 중..."
cd ../server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

wait