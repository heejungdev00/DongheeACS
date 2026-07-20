import asyncio
import logging

logger = logging.getLogger(__name__)


class AntConnector:
    """
    ANT server 연결 상태를 관리하고
    끊어지면 자동으로 재연결을 시도합니다.
    """
    def __init__(self, ant_client, username, password,
                 on_status_change=None, retry_interval=10):
        self.ant              = ant_client
        self.username         = username
        self.password         = password
        self.on_status_change = on_status_change
        self.retry_interval   = retry_interval

    async def start(self):
        """서버 시작과 함께 백그라운드에서 계속 실행"""
        while True:
            if not self.ant.is_ready():
                await self._try_connect()
            else:
                # 연결된 상태에서도 주기적으로 헬스체크
                await self._health_check()

            await asyncio.sleep(self.retry_interval)

    async def _try_connect(self):
        logger.info("ANT server 연결 시도 중...")
        try:
            token, api_version = await self.ant.login(
                self.username, self.password
            )
            if token:
                logger.info("ANT server 연결 성공")
                logger.info(f"api_version은 이거야------------------------ {api_version}")
                if self.on_status_change:
                    await self.on_status_change(True)
            else:
                logger.warning(
                    f"ANT server 연결 실패 "
                    f"({self.retry_interval}초 후 재시도)"
                )
        except Exception as e:
            logger.warning(f'ANT server 연결 예외: {e} ({self.retry_interval}초 후 재시도)')
            self.ant.connected = False
            self.ant.token = None

    async def _health_check(self):
        """
        연결된 상태에서 실제로 살아있는지 확인
        get_vehicles 가 None 이면 연결이 끊긴 것으로 판단
        """
        try:
            result = await self.ant.get_vehicles()
            if result is None:
                raise ConnectionError("응답 없음")
        except Exception as e:
            logger.warning(f"ANT server 헬스체크 실패: {e}")
            self.ant.connected = False
            self.ant.token     = None
            if self.on_status_change:
                await self.on_status_change(False)