import asyncio
import logging
import json

logger = logging.getLogger(__name__)

# ANT server navigationstate 값 (매뉴얼 G 1.1.8)
NAV_PLANNED   = 1   # Accepted/Planned
NAV_REJECTED  = 2   # Rejected
NAV_RUNNING   = 3   # Started/Running
NAV_DONE      = 4   # Completed/Terminated
NAV_CANCELLED = 5   # Cancelled

MAX_RETRY = 10


class MissionMonitor():
    def __init__(self, ant, db, ws_manager, plc_poller, signal_map):
        self.ant        = ant
        self.db         = db
        self.ws         = ws_manager
        self.poller     = plc_poller
        self.signal_map = {s["mission_case"]: s for s in signal_map}

    async def start(self, interval: float = 10.0):
        while True:
            await asyncio.sleep(interval)
            await self._check_running_missions()

    async def _check_running_missions(self):
        running = self.db.get_running_missions()
        if not running:
            return

        # mock 또는 ANT 미연결이면 스킵
        if not self.ant.is_ready():
            logger.debug("ANT server 미연결 - 미션 모니터 스킵")
            return

        if getattr(self.ant, 'token', None) == 'mock-token':
            logger.debug("Mock 모드 - 미션 모니터 스킵")
            return

        for tracked in running:
            mission_id  = str(tracked["mission_id"])
            signal      = tracked["signal"]
            retry_count = tracked["retry_count"]

            await self._check_single_mission(mission_id, signal, retry_count)

    async def _check_single_mission(self, mission_id, signal, retry_count):
        """
        미션 하나의 상태를 개별 조회해서 판단.
        GET /wms/rest/{api_version}/missions/{mission_id}
        """
        try:
            result = await self.ant.get_mission(mission_id)
        except Exception as e:
            logger.error(f"미션 {mission_id} 조회 예외: {e}")
            return

        if result is None:
            logger.error(f"미션 {mission_id} 조회 실패: 응답 없음")
            return

        # 매뉴얼 G 1.1.9: payload.missions 배열로 반환
        # missions = result.get("payload", {}).get("missions", [])
        if not result:
            logger.warning(f"미션 {mission_id} 조회 결과 없음 - 재시도 연기")
            return

        mission     = result[0]
        nav_state   = mission.get("navigationstate")
        trans_state = mission.get("transportstate")

        logger.debug(
            f"미션 {mission_id} 상태 확인: "
            f"navigationstate={nav_state}, transportstate={trans_state}"
        )

        # ── 정상 완료 ──────────────────────────────────────
        if nav_state == NAV_DONE:
            logger.info(f"미션 {mission_id} 완료 (Terminated)")
            self.db.update_mission_status(mission_id, "DONE")

            if isinstance(signal, dict) and 'mission_case' in signal:
                mission_case = signal['mission_case']
                logger.info(f'PLC 레지스터에 완료 신호(2) 전송 시작 - Mission Case: {mission_case}')

                asyncio.create_task(self.poller.trigger_mission_clear_pulse(mission_case))
            
            else:
                logger.warning(f"미션 {mission_id}의 signal 데이터에서 mission_case를 찾을 수 없어 PLC 펄스를 건너뜁니다.")

            await self.ws.broadcast({
                "type"      : "mission_done",
                "mission_id": mission_id,
                "signal"    : signal,
            })

        # ── 취소 또는 거부 → 재생성 ────────────────────────
        elif nav_state in (NAV_CANCELLED, NAV_REJECTED):
            reason = "취소됨" if nav_state == NAV_CANCELLED else "거부됨"
            logger.warning(f"미션 {mission_id} {reason} → 재생성 시도")
            await self._handle_retry(mission_id, signal, retry_count)

        # ── 계획됨 또는 실행 중 → 계속 모니터링 ────────────
        elif nav_state in (NAV_PLANNED, NAV_RUNNING):
            logger.debug(
                f"미션 {mission_id} "
                f"{'계획됨' if nav_state == NAV_PLANNED else '실행 중'} - 모니터링 계속"
            )

        # ── 알 수 없는 상태 ─────────────────────────────────
        else:
            logger.warning(
                f"미션 {mission_id} 알 수 없는 상태: "
                f"navigationstate={nav_state}"
            )

    async def _handle_retry(self, mission_id, signal, retry_count):
        """재시도 처리"""
        if retry_count >= MAX_RETRY:
            logger.error(
                f"미션 {mission_id} 최대 재시도 {MAX_RETRY}회 초과 → FAILED"
            )
            self.db.update_mission_status(mission_id, "FAILED")

            await self.ws.broadcast({
                "type"      : "mission_failed",
                "mission_id": mission_id,
                "signal"    : signal,
                "message"   : f"최대 재시도({MAX_RETRY}회) 초과",
            })
            return

        if not self.ant.is_ready():
            logger.warning("ANT server 미연결 - 재생성 연기")
            return

        self.db.update_mission_status(mission_id, "RETRYING")
        self.db.increment_retry(mission_id)

        try:
            mission_data = {
                "missionrequest": {
                    "requestor": "admin",
                    "missiontype": 7,
                    "fromnode": signal.get("fromnode"),
                    "tonode": signal.get("tonode"),
                    "cardinality": 1,
                    "priority": 2,
                    "deadline" : None,
                    "parameters": {
                        "desc": "Mission extension",
                        "type": "org.json.JSONObject",
                        "name": "parameters",
                        "value": {
                            "payload": "Default Payload",
                            "dynamicnodetypes" : {
                                "fromnodetype" : {
                                    "name" : "Pick",
                                    "vars" : {
                                        'height1' : signal.get("fromh1"),
                                        'height2' : signal.get("fromh2")
                                    }
                                },
                                "tonodetype" : {
                                    "name" : "Drop",
                                    "vars" : {
                                        'height1' : signal.get("toh1"),
                                        'height2' : signal.get("toh2")
                                    }
                                }
                            }

                        }
                    }
                }
            }
            logger.info(json.dumps(mission_data))

            result = await self.ant.create_mission(mission_data=mission_data)
            if result is None:
                logger.error("미션 재생성 실패: ANT server 응답 없음")
                self.db.update_mission_status(mission_id, "RUNNING")
                return

            accepted = result.get("payload", {}).get("acceptedmissions", [])

            if accepted:
                new_id = str(accepted[0])
                logger.info(
                    f"미션 재생성 성공: "
                    f"구={mission_id} → 신={new_id} "
                    f"({retry_count + 1}/{MAX_RETRY})"
                )
                self.db.update_mission_status(mission_id, "RETRIED")
                self.db.track_mission(new_id, signal)

                await self.ws.broadcast({
                    "type"          : "mission_retried",
                    "old_mission_id": mission_id,
                    "new_mission_id": new_id,
                    "signal"        : signal,
                })
            else:
                logger.error(f"미션 재생성 거부됨: {result}")
                self.db.update_mission_status(mission_id, "RUNNING")

        except Exception as e:
            logger.error(f"미션 재생성 예외: {e}")
            self.db.update_mission_status(mission_id, "RUNNING")