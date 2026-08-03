import asyncio
import logging
from pymodbus.client import ModbusTcpClient

logger = logging.getLogger(__name__)

mission_case_map = {
    # (source_pos, target_pos) : mission_case
    (2, 3): 0,
    (2, 4): 1,
    (3, 2): 2,
    (4, 2): 3
}

AFL_STATUS_MAP = {
    0: 0, 1: 1, 2: 2,
    3: 3, 4: 4, 6: 99
}

LIDAR_ERROR_MAP = {
    'LSC_F_Danger': 1, 'LSC_L_Danger': 2, 'LSC_R_Danger': 3, 'LSC_T_Danger': 4,
    'LSC_F_Error': 5, 'LSC_L_Error': 6, 'LSC_R_Error': 7, 'LSC_T_Error': 8
}

PLATFORM_ERROR_MAP = {
    'Error Lift SNR': 1, 'Error Lifting': 2, 'Error Tilting': 3, 'Error Siding': 4,
    'Interlock': 5, 'EMS': 6, 'Door': 7, 'Bumper': 8,
    'PLC Interlock': 9
}

SENSOR_ERROR_MAP = {
    'Safety Forktip Detected Obstacle': 1,
    'Safety Load Detected Unload': 2,
    'Safety Load Detected Load': 3
}

# ---------------------------------------------------------------------------
# Modbus 레지스터 블록 정의
#   READ  : 50~76 (미션 정보 50-53, 진입허가 54-56, 일시정지 58, 미션트리거 76) -> 한번에 read
#   WRITE : 70~86 (상태/미션FB/트리거ack/미션결과/알람/점유) -> 한번에 write
# 59~75 구간 중 일부는 사용하지 않는 예비 주소지만, 하나의 read 트랜잭션으로
# 묶기 위해 통째로 읽어옵니다. (PLC 쪽에 해당 주소 범위가 모두 정의되어 있어야 함)
# ---------------------------------------------------------------------------
READ_START = 50
READ_COUNT = 27   # 50 ~ 76
WRITE_START = 70
WRITE_COUNT = 17  # 70 ~ 86


class ModbusPoller:
    def __init__(self, ant_client, host, port, signal_map,
                 on_trigger, on_status_change=None):
        self.host = host
        self.ant = ant_client
        self.port = port
        self.signal_map = signal_map
        self.on_trigger = on_trigger
        self.on_status_change = on_status_change
        self.cached_vehicle_data = None
        self.cached_occupy_vals = {}
        
        self.client = None
        self.connected = False

        # 하트비트 토글 상태 변수
        self.hb_state = 0
        self.prev_trigger = 0
        self.current_mission_id_fb = 0  # 75번 주소 피드백 용
        self.next_mission_id = 0  # 다음 미션 id 임시 보관용

        self.mission_results = [0, 0, 0, 0]
        self.pulse_locks = {77: False, 78: False, 79: False, 80: False}

        self.last_pause_plc_state = None  # 58번 레지스터의 이전 상태 저장용 (None, 0, 1)

        # 진입 허가(PLC -> Device) 이전 값 추적용
        self.last_enter_plc_states = {54: None, 55: None, 56: None}
        self.enter_mapping = {
            54: "enter_MAP",
            55: "enter_LH",
            56: "enter_RH"
        }

        # 점유 상태(Device -> PLC) 이전 값 추적용
        self.last_occupy_device_states = {"occupy_LH": None, "occupy_MAP": None, "occupy_RH": None}
        self.occupy_mapping = {
            "occupy_MAP": 84,
            "occupy_LH": 85,
            "occupy_RH": 86
        }

        # ANT 응답이 없을 때 직전 값을 유지하기 위한 캐시
        self._last_afl_status = 0
        self._last_current_pos = 0
        self._last_load_state = 0
        self._last_battery = 0

    def _make_client(self):
        return ModbusTcpClient(
            host=self.host,
            port=self.port,
            timeout=1.0,
            retries=0
        )

    async def start(self, interval: float = 1.0):
        logger.info('modbuspoller 루프시작 (단일 read/write 사이클)')
        try:
            await self._poll_cycle(interval)
        except Exception as e:
            logger.critical(f'poll cycle 내부에서 치명적인 예외 발생: {e}')

    # 1. ANT 상태를 주기적으로 갱신하는 별도 루프 (Modbus 루프와 분리)
    async def _update_ant_cache_loop(self):
        while True:
            try:
                if self.ant.is_ready():
                    occupy_names = list(self.occupy_mapping.keys())
                    gathered = await asyncio.gather(
                        self.ant.get_vehicles(),
                        *[self.ant.read_device_io_value(name) for name in occupy_names],
                        return_exceptions=True
                    )
                    
                    vd, *occ_results = gathered
                    if not isinstance(vd, Exception):
                        self.cached_vehicle_data = vd[0] if isinstance(vd, list) and vd else vd
                    
                    for name, val in zip(occupy_names, occ_results):
                        if not isinstance(val, Exception) and val is not None:
                            self.cached_occupy_vals[name] = int(val)
            except Exception as e:
                logger.error(f"ANT 캐시 갱신 오류: {e}")
            
            await asyncio.sleep(0.5) # ANT 수집 주기 (PLC와 독립적으로 동작)

    async def _write_registers_async(self, address: int, values: int) -> bool:
            """Holding Register에 값을 동기식 라이브러리 기반으로 안전하게 Write하는 헬퍼 함수"""
            if not self.connected or self.client is None:
                return False
            try:
                # pymodbus 최신 버전에서는 slave 인수 등을 키워드로 안전하게 넘길 수 있습니다.
                result = self.client.write_registers(address=address, values=values)
                if result is None or result.isError():
                    logger.error(f"Register 쓰기 에러: addr={address}, val={values}")
                    return False
                return True
            except Exception as e:
                logger.error(f"Register 쓰기 예외 발생: addr={address}, err={e}")
                return False

    async def _poll_cycle(self, interval: float):
        # background로 ant 캐시 루프 실행
        asyncio.create_task(self._update_ant_cache_loop())

        '''
        기존에 5개의 독립된 asyncio 루프(_poll, write_vehicle_status,
        sync_enter_permissions, monitor_occupy_devices, monitor_vehicle_pause)가
        각자 필요할 때마다 self.client 로 개별 read/write 를 호출하던 구조를
        "PLC 전체 read 1회 -> 로직 처리 -> PLC 전체 write 1회" 사이클 하나로 통합.

        - 여러 코루틴이 동시에 같은 동기식 ModbusTcpClient 소켓을 두드리던
          문제(락 없이 공유)가 구조적으로 사라짐 (단일 루프 = 단일 접근자).
        - 다만 모든 감시항목(진입허가/일시정지/점유상태/미션트리거)이 같은
          interval 로 폴링됨. 기존에 0.5s로 더 촘촘히 돌던 pause 감시가
          필요하면 interval 자체를 그만큼 짧게 넘겨야 함.
        '''
        while True:
            try:
                # 0. 연결 확인 및 재연결
                if not self.connected:
                    self.client = self._make_client()
                    ok = self.client.connect()
                    if not ok:
                        raise ConnectionError("Modbus 연결 실패")
                    self.connected = True
                    logger.info(f"PLC 연결 성공: {self.host}:{self.port}")
                    if self.on_status_change:
                        await self.on_status_change(True)

                # -----------------------------------------------------------
                # 1) PLC -> Middleware 값 전체를 한번에 READ (50~76, 27개)
                # -----------------------------------------------------------
                read_result = self.client.read_holding_registers(address=READ_START, count=READ_COUNT)
                if read_result is None or read_result.isError():
                    raise ConnectionError("PLC 레지스터 일괄 읽기 실패 (50~76)")

                regs = read_result.registers

                def R(addr):
                    return regs[addr - READ_START]

                mission_id_in = R(50)
                command_in = R(51)
                source_pos_in = R(52)
                target_pos_in = R(53)
                enter_vals = {54: R(54), 55: R(55), 56: R(56)}
                pause_in = R(58)
                trigger_in = R(76)
                logger.info('레지스터 읽기 성공@@@')

                # -----------------------------------------------------------
                # 2) ANT 서버 쪽 값도 동시에 한번에 READ (vehicle 상태 + 점유 디바이스)
                # -----------------------------------------------------------
                vehicle_data = getattr(self, 'cached_vehicle_data', None)
                occupy_vals = getattr(self, 'cached_occupy_vals', {}).copy()
                logger.info(f'vehicle dat는 : {vehicle_data}')
                logger.info(f'occupy_vals는 : {occupy_vals}')

                # -----------------------------------------------------------
                # 3) 로직 처리 (기존 5개 루프의 판단 로직을 이 자리로 통합)
                # -----------------------------------------------------------

                # 3-1. 하트비트 토글
                self.hb_state = 1 if self.hb_state == 0 else 0

                # 3-2. 진입 허가 동기화 (값이 바뀐 경우에만 ANT로 명령 전달)
                for reg_addr, current_val in enter_vals.items():
                    device_name = self.enter_mapping[reg_addr]
                    if (self.last_enter_plc_states[reg_addr] is None) or (current_val != self.last_enter_plc_states[reg_addr]):
                        logger.info(f"🔄 PLC 진입 허가 변경 감지 (HR {reg_addr}): {self.last_enter_plc_states[reg_addr]} -> {current_val}")
                        try:
                            resp = await self.ant.write_device(device_name, current_val)
                            if isinstance(resp, dict) and resp.get('retcode') == 0:
                                self.last_enter_plc_states[reg_addr] = current_val
                                logger.info(f"✅ 진입 허가 반영 완료 (HR {reg_addr}) -> {current_val}")
                            else:
                                logger.error(f"❌ ANT 서버 장치({device_name}) 반영 실패! 다음 주기에 재시도")
                        except Exception as e:
                            logger.error(f"진입 허가 write_device 예외: {e}")

                # 3-3. Pause / Resume
                if (self.last_pause_plc_state is None) or (pause_in != self.last_pause_plc_state):
                    if pause_in == 1:
                        logger.warning("🚨 PLC HR 58 제동 신호 감지 (1) -> Forklift 일시정지(Pause) 명령 송신")
                        res = await self.ant.pause_vehicle()
                        logger.info(f"Pause API 결과: {res}")
                    elif pause_in == 0:
                        if self.last_pause_plc_state is not None:
                            logger.info("▶ PLC HR 58 제동 해제 감지 (0) -> Forklift 이동 재개(Resume) 명령 송신")
                            res = await self.ant.resume_vehicle()
                            logger.info(f"Resume API 결과: {res}")
                        else:
                            logger.info("초기 가동 상태 58번=0 확인 (대기)")
                    self.last_pause_plc_state = pause_in


                # 3-4. 미션 트리거 처리 (0 -> 1 로 변하는 시점)
                trigger_out = trigger_in
                if trigger_in == 1 and self.prev_trigger == 0:
                    logger.info(
                        f'Plc 미션 트리거 감지! ID={mission_id_in}, Cmd={command_in}, '
                        f'Src={source_pos_in}, Tgt={target_pos_in}'
                    )

                    if not any(res in [1, 2] for res in self.mission_results):
                        self.current_mission_id_fb = mission_id_in
                        self.next_mission_id = mission_id_in
                    else:
                        self.next_mission_id = mission_id_in

                    mission_case = mission_case_map.get((source_pos_in, target_pos_in), -1)
                    if 0 <= mission_case <= 3:
                        self.mission_results[mission_case] = 1
                        logger.info(f'미션케이스 {mission_case} 시작 -> 레지스터 {77 + mission_case}=1 (다음 write에 반영)')

                    matched = False
                    for sig in self.signal_map:
                        if sig.get('mission_case') == mission_case:
                            logger.info(f"매칭완료 (Case {mission_case}): {sig.get('fromnode')} -> {sig.get('tonode')}")
                            await self.on_trigger(sig)
                            matched = True
                            break
                    if not matched:
                        logger.warning(f'target signal 없음. mission_case={mission_case}')

                    # ack: 다음 write 사이클에 76번을 0으로 내려보냄
                    trigger_out = 0

                self.prev_trigger = trigger_out

                # 3-5. 차량 상태 계산 (ANT 응답 -> 레지스터 값). 응답이 없으면 직전 값 유지
                if vehicle_data:
                    ant_status = vehicle_data.get('operatingstate', 0)
                    logger.info(f'ant_status : {ant_status}')
                    afl_status = AFL_STATUS_MAP.get(ant_status, 0)
                    logger.info(f'afl_status : {afl_status}')

                    location = vehicle_data.get('location', {}) or {}
                    current_pos = location.get('currentnodeid') or 0

                    load_state = 1 if vehicle_data.get('isloaded', 0) else 0
                    logger.info(f'현재 로드데이터는 : {vehicle_data.get('isloaded')}')

                    battery_info = vehicle_data.get('state', {}).get('battery.info', ["0", "0"])
                    battery = int(float(battery_info[0])) if battery_info else 0

                    logger.info(f'battery : {battery}')

                    alarms = vehicle_data.get('alarms', [])

                    logger.info(f'alarm은 -----------{alarms}')
                    lidar_err = platform_err = sensor_err = 0
                    for alarm in alarms:
                        if not lidar_err and alarm in LIDAR_ERROR_MAP:
                            lidar_err = LIDAR_ERROR_MAP[alarm]
                        if not platform_err and alarm in PLATFORM_ERROR_MAP:
                            platform_err = PLATFORM_ERROR_MAP[alarm]
                        if not sensor_err and alarm in SENSOR_ERROR_MAP:
                            sensor_err = SENSOR_ERROR_MAP[alarm]

                    self._last_afl_status = afl_status
                    self._last_current_pos = current_pos
                    self._last_load_state = load_state
                    self._last_battery = battery

                else:
                    afl_status = self._last_afl_status
                    current_pos = self._last_current_pos
                    load_state = self._last_load_state
                    battery = self._last_battery
                    lidar_err = platform_err = sensor_err = 0


                # 3-6. 점유 상태 갱신 (읽어온 값이 있을 때만 갱신, 없으면 직전 값 유지)
                for name in self.occupy_mapping:
                    if name in occupy_vals:
                        if self.last_occupy_device_states[name] != occupy_vals[name]:
                            logger.info(f"🚨 디바이스 점유 상태 변경 감지 ({name}): "
                                        f"{self.last_occupy_device_states[name]} -> {occupy_vals[name]}")
                        self.last_occupy_device_states[name] = occupy_vals[name]
                logger.info(f'여기를 지나가느냐6666666666666666666')
                # -----------------------------------------------------------
                # 4) Middleware -> PLC 값 전체를 한번에 WRITE (70~86, 17개)
                # -----------------------------------------------------------
                output_values = [
                    afl_status,                                                # 70
                    self.hb_state,                                             # 71
                    current_pos,                                               # 72
                    load_state,                                                # 73
                    battery,                                                   # 74
                    self.current_mission_id_fb,                                # 75
                    trigger_out,                                               # 76
                    self.mission_results[0],                                   # 77
                    self.mission_results[1],                                   # 78
                    self.mission_results[2],                                   # 79
                    self.mission_results[3],                                   # 80
                    lidar_err,                                                 # 81
                    platform_err,                                              # 82
                    sensor_err,                                                # 83
                    self.last_occupy_device_states.get('occupy_MAP') or 0,     # 84
                    self.last_occupy_device_states.get('occupy_LH') or 0,      # 85
                    self.last_occupy_device_states.get('occupy_RH') or 0,      # 86
                ]
                logger.info(f'write 값 직렬화 : {output_values}')

                await self._write_registers_async(WRITE_START, output_values)

                await asyncio.sleep(interval)

            except Exception as e:
                if self.connected:
                    self.connected = False
                    logger.warning(f"PLC 연결 끊김: {e}")
                    if self.on_status_change:
                        await self.on_status_change(False)

                if self.client:
                    self.client.close()
                self.client = None
                self.prev_trigger = 0
                await asyncio.sleep(5)

    async def trigger_mission_clear_pulse(self, mission_case: int):
        '''
        특정 미션 케이스 완료 시 호출.
        기존에는 이 함수가 직접 레지스터를 write 했지만, 이제는
        self.mission_results 상태만 갱신하고, 실제 PLC 반영은
        메인 사이클의 일괄 write 에 맡긴다 (read/write 를 한 곳에서만 수행).

        주의: interval 이 1.5초보다 충분히 짧아야 PLC 쪽에서 "2" 값을
        최소 1회 이상 관측할 수 있음.
        '''
        if not (0 <= mission_case <= 3):
            logger.warning(f'유효하지 않은 미션 케이스 번호: {mission_case}')
            return

        target_reg = 77 + mission_case
        try:
            logger.info(f'미션 완료 신호 감지 (Case {mission_case} -> Reg {target_reg})')
            self.mission_results[mission_case] = 2

            await asyncio.sleep(1.5)

            if self.mission_results[mission_case] == 2:
                self.mission_results[mission_case] = 0
                self.current_mission_id_fb = self.next_mission_id
                logger.info(f'📢 미션 완료 처리 -> mission_id_fb={self.current_mission_id_fb} (다음 write 사이클 반영)')
            else:
                logger.warning(f'Case {mission_case} 완료 펄스 유지 중 새 작업(1)이 인입되어 0 원복을 생략합니다.')
        finally:
            self.pulse_locks[target_reg] = False