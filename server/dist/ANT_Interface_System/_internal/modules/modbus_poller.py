import asyncio
import logging
from pymodbus.client import ModbusTcpClient

logger = logging.getLogger(__name__)
mission_case_map = {
    # (source_pos, target_pos) : mission_case
    (2,3):0,
    (2,4):1,
    (3,2):2,
    (4,2):3
}


AFL_STATUS_MAP = {
    0: 0, 1: 1, 2: 2,
    3: 3, 4: 4, 6: 99
}

LIDAR_ERROR_MAP = {
    'LSC_F_Danger': 1, 'LSC_L_Danger': 2, 'LSC_R_Danger': 3, 'LSC_T_Danger': 4,
    'LSC_F_Error' : 5, 'LSC_L_Error' : 6, 'LSC_R_Error' : 7, 'LSC_T_Error' : 8
}

PLATFORM_ERROR_MAP = {
    'Error Lift SNR': 1, 'Error Lifting': 2, 'Error Tilting': 3, 'Error Siding': 4,
    'Interlock'     : 5, 'EMS'          : 6, 'Door'         : 7, 'Bumper'       : 8,
    'PLC Interlock' : 9
}

SENSOR_ERROR_MAP = {
    'Safety Forktip Detected Obstacle': 1,
    'Safety Load Detected Unload'     : 2,
    'Safety Load Detected Load'       : 3
}

class ModbusPoller:
    def __init__(self, ant_client, host, port, signal_map,
                 on_trigger, on_status_change=None):
        self.host             = host
        self.ant              = ant_client
        self.port             = port
        self.signal_map       = signal_map
        self.on_trigger       = on_trigger
        self.on_status_change = on_status_change
        self.client           = None
        self.connected        = False

        # plc 통신 동기화용 비동기 락
        # self.modbus_lock = asyncio.Lock()

        #하트비트 토글 상태 변수
        self.hb_state = 0
        self.prev_trigger = 0
        self.current_mission_id_fb = 0 # 75번 주소 피드백 용
        self.next_mission_id = 0 # 다음 미션 id 임시 보관용

        self.mission_results = [0, 0, 0, 0]
        self.pulse_locks = {77: False, 78: False, 79: False, 80: False}

        self.last_pause_plc_state = None # 58번 레지스터의 이전 상태 저장용 (None, 0, 1)

        # 진입 허가(PLC -> Device) 이전 값 추적용 (초기값은 None 또는 임의의 값)
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



    def _make_client(self):
        return ModbusTcpClient(
            host    = self.host,
            port    = self.port,
            timeout = 3,
        )

    async def start(self, interval: float = 1.0):
        logger.info('modbuspoller 루프시작') 
        try:
            await asyncio.gather(
                self._poll(interval),
                self.write_vehicle_status(interval),
                self.sync_enter_permissions(),
                self.monitor_occupy_devices(),
                self.monitor_vehicle_pause()
            )
        except Exception as e:
            logger.critical(f'gather 내부에서 치명적인 예외 발생: {e}')


    async def _poll(self, interval: float):
        while True:
            try:
                # 1. 연결 확인 및 재연결
                if not self.connected:
                    self.client = self._make_client()
                    ok = self.client.connect()
                    if not ok:
                        raise ConnectionError("Modbus 연결 실패")

                    self.connected = True
                    logger.info(f"PLC 연결 성공: {self.host}:{self.port}")
                    if self.on_status_change:
                        await self.on_status_change(True)
                
                # 2. heartbeat (AFL_Heartbeat -> 40001에 0/1 토글)
                await self._handle_middleware_heartbeat()


                # 3. Command_Trigger(76)
                trigger_result = self.client.read_holding_registers(address=76, count=1)

                if trigger_result is None or trigger_result.isError():
                    raise ConnectionError('Trigger 레지스터 76 읽기실패')

                current_trigger = trigger_result.registers[0]

                # 4. Trigger가 0 -> 1 로 변하는 시점에 미션 생성
                if current_trigger == 1 and self.prev_trigger == 0:

                    # 4.1 PLC 데이터 일괄 읽기 (주소 50-54 연속된 영역 읽기)
                    result = self.client.read_holding_registers(address=50, count=4)

                    if result is None or result.isError():
                        raise ConnectionError("PLC 레지스터 읽기 실패")

                    # 레지스터 값 추출
                    mission_id = result.registers[0]
                    command = result.registers[1]
                    source_pos = result.registers[2]
                    target_pos = result.registers[3]


                    logger.info(f'Plc 미션 트리거 감지! ID={mission_id}, Cmd={command}, Src={source_pos}, Tgt={target_pos}')

                    if not any(res in [1,2] for res in self.mission_results):
                        self.current_mission_id_fb = mission_id
                        # 피드백 용 변수에 미션 id 즉시 복사 75번 기입
                        self.next_mission_id = mission_id
                        
                        await self._write_register_async(75, mission_id) # 바로 업데이트 X

                    else:
                        self.next_mission_id = mission_id

                    # 4.2 mission_case 값 계산
                    mission_case = mission_case_map.get((source_pos, target_pos), -1)

                    # 미션 결과를 1로 세팅
                    if 0 <= mission_case <= 3:
                        self.mission_results[mission_case] = 1
                        target_reg = 77 + mission_case
                        await self._write_register_async(target_reg, 1)
                        logger.info(f'미션케이스 {mission_case}  시작 -> plc {target_reg}번 레지스터 1로 변경 완료') 

                    # 4.3 signal_map 이전
                    for sig in self.signal_map:
                        if sig.get('mission_case') == mission_case:
                            logger.info(f'매칭완료 (Case {mission_case}): {sig.get('fromnode')} -> {sig.get('tonode')}')
                            await self.on_trigger(sig)
                            break
                        else:
                            logger.warning(f'target signal 없음 미션케이스: case{mission_case}, sig.get{sig.get('mission_case')}')
                            
                    
                    # mission_trigger를 0으로 변경하여 ack 처리
                    success = await self._write_register_async(76, 0)
                    if success:
                        logger.info('Command_Trigger 76 클리어완료 (->0)')
                        current_trigger = 0

                        await asyncio.sleep(0.3)

                # 트리거 상태 업데이트
                self.prev_trigger = current_trigger            

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
                self.prev_trigger   = 0
                await asyncio.sleep(5)

    async def _handle_middleware_heartbeat(self):
        'AFL_Heartbeat(71)에 1초마다 0과 1을 번갈아가며 write'
        self.hb_state = 1 if self.hb_state == 0 else 0
        success = await self._write_register_async(71, self.hb_state)
        if not success:
            logger.warning('AFL_Heartbeat 쓰기 실패')

    async def _write_register_async(self, address: int, value: int) -> bool:
        """Holding Register에 값을 동기식 라이브러리 기반으로 안전하게 Write하는 헬퍼 함수"""
        if not self.connected or self.client is None:
            return False
        try:
            # pymodbus 최신 버전에서는 slave 인수 등을 키워드로 안전하게 넘길 수 있습니다.
            result = self.client.write_register(address=address, value=value)
            if result is None or result.isError():
                logger.error(f"Register 쓰기 에러: addr={address}, val={value}")
                return False
            return True
        except Exception as e:
            logger.error(f"Register 쓰기 예외 발생: addr={address}, err={e}")
            return False
        
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
        
    async def write_vehicle_status(self, interval):
        '''
        ANT server API응답 받아서
        주소에 일괄 write
        '''
        while True:

            try:
                if not self.ant.is_ready():
                    await asyncio.sleep(interval)
                    continue

                # 1. ant 서버에서 실시간 vehicle 정보 가져오기
                vehicle_data = await self.ant.get_vehicles()
                if not vehicle_data:
                    await asyncio.sleep(interval)
                    continue

                if isinstance(vehicle_data, list):
                    if len(vehicle_data) > 0:
                        vehicle_data = vehicle_data[0]
                    else:
                        return

                # 70: AFL_status
                ant_status = vehicle_data.get('operatingstate', 0)
                afl_status = AFL_STATUS_MAP.get(ant_status, 0)

                # 72: AFL_CurrentPos
                location = vehicle_data.get('location', {})
                logger.info(f'vehicle 현재 위치는: {location}')
                current_pos = location.get('currentnodeid')
                # current_pos = current_node_obj.get('id', 1)

                # 73: 
                load_state = 1 if vehicle_data.get('isloaded',0) else 0
                logger.info(f'현재 로드데이터는 : {vehicle_data.get('isloaded')}')      

                # 74: AFL_Battery
                battery_info = vehicle_data.get('state', {}).get('battery.info', ["0", "0"])
                battery = int(float(battery_info[0]))

                # 75: AFL_Mission_ID_FB (50번 미션 id 복사)

                # 77-80: AFL_Mission_Reslt

                # 81-83: 알람/에러 매핑 (가장 먼저 발생한 1개 매핑
                alarms = vehicle_data.get('alarms', [])
                msgs = vehicle_data.get('messages', [])

                logger.info(f'alarms: {alarms}')
                logger.info(f'msgs: {msgs}')

                lidar_err = 0
                platform_err = 0
                sensor_err = 0

                for alarm in alarms:
                    if not lidar_err and alarm in LIDAR_ERROR_MAP:
                        lidar_err = LIDAR_ERROR_MAP[alarm]
                    if not platform_err and alarm in PLATFORM_ERROR_MAP:
                        platform_err = PLATFORM_ERROR_MAP[alarm]
                    if not sensor_err and alarm in SENSOR_ERROR_MAP:
                        sensor_err = SENSOR_ERROR_MAP[alarm]

                await self._write_registers_async(70, [
                    afl_status,
                    self.hb_state,
                    current_pos,
                    load_state,
                    battery,
                    self.current_mission_id_fb                   
                ])

                await self._write_registers_async(77, [
                    self.mission_results[0],
                    self.mission_results[1],
                    self.mission_results[2],
                    self.mission_results[3],
                ])

                await self._write_registers_async(81, [lidar_err, platform_err, sensor_err])



            except Exception as e:
                logger.error(f'AFL 상태 write 루프 에러: {e}')
        
            await asyncio.sleep(interval)

    async def trigger_mission_clear_pulse(self, mission_case: int):
        '''특정 미션 케이스 번호가 완료되었을 때 호출되어 개별 레지스터에 1.5초 펄스'''
        if not (0 <= mission_case <= 3):
            logger.warning(f'유효하지 않은 미션 케이스 번호: {mission_case}')
            return
        
        target_reg = 77 + mission_case  # Case 0=77, 1=78, 2=79, 3=80

        try:
            logger.info(f'미션 완료 신호 감지 (Case {mission_case} -> Reg {target_reg})')

            # 1. 완료 신호인 2 기록
            self.mission_results[mission_case] = 2
            await self._write_register_async(target_reg, 2)

            # 2. 1.5초 대기
            await asyncio.sleep(1.5)

            # 3. 0으로 복구
            if self.mission_results[mission_case] == 2:
                self.mission_results[mission_case] = 0
                await self._write_register_async(target_reg, 0)
                logger.info(f'plc {target_reg}번 pulse 종료 ->0 으로 복구 완료')

                self.current_mission_id_fb = self.next_mission_id
                await self._write_register_async(75, self.current_mission_id_fb)
                logger.info(f'📢 미션 완료 처리 완료 -> PLC 75번 피드백 ID를 {self.current_mission_id_fb}로 업데이트했습니다.')
            else:
                logger.warning(f'PLC {target_reg}번 완료 펄스 유지 중 새 작업(1)이 인입되어 0 원복을 생략합니다.')

        finally:
            self.pulse_locks[target_reg] = False


    async def sync_enter_permissions(self):
        """
        [태스크 1] PLC HR 54~56번을 감시하여 enter_* 디바이스로 상태를 동기화합니다.
        기존 PLC 폴링 주기와 싱크를 맞추거나 적절한 주기로 실행합니다.
        """
        logger.info("PLC 진입 허가(54~56) -> Device 동기화 루프 시작")
        while True:
            try:
                # 54번 주소부터 3개의 레지스터(54, 55, 56) 읽기
                # (기존에 구현해 두신 단건 또는 일괄 읽기 함수가 있다면 그것을 활용하셔도 됩니다)
                response = self.client.read_holding_registers(address=54, count=3)
                if response and not response.isError():
                    regs = response.registers  # [54번값, 55번값, 56번값]
                    
                    for idx, reg_addr in enumerate([54, 55, 56]):
                        current_plc_val = regs[idx]
                        device_name = self.enter_mapping[reg_addr]
                        
                        # 상태가 변경되었을 때만 Device에 쓰기 수행
                        if (self.last_enter_plc_states[reg_addr] is None) or (current_plc_val != self.last_enter_plc_states[reg_addr]):
                            logger.info(f"🔄 PLC 진입 허가 변경 감지 (HR {reg_addr}): {self.last_enter_plc_states[reg_addr]} -> {current_plc_val}")
                            
                            # Device에 0 또는 1 명령 전달
                            response_data = await self.ant.write_device(device_name, current_plc_val)
                            
                            if isinstance(response_data, dict) and response_data.get('retcode') == 0:
                            # 최근 상태 갱신
                                self.last_enter_plc_states[reg_addr] = current_plc_val
                                logger.info(f"✅ PLC 진입 허가 변경 완료 (HR {reg_addr}): {self.last_enter_plc_states[reg_addr]} -> {current_plc_val}")
                            else:
                                logger.error(f'❌ ANT 서버 장치({device_name}) 반영 실패! 다음 주기에 재시도')
            except Exception as e:
                logger.error(f"진입 허가 동기화 루프 에러: {e}")
            
            # 주기는 시스템 상황에 맞게 조절 (예: 0.5초 또는 1초)
            await asyncio.sleep(1)

    async def monitor_occupy_devices(self):
        """
        [태스크 2] occupy_* 디바이스 상태를 1초 주기로 폴링하여 PLC HR 84~86번에 반영합니다.
        """
        logger.info("Device 점유 상태(occupy) -> PLC HR(84~86) 동기화 루프 시작 (주기: 1s)")
        while True:
            try:
                for device_name, target_reg in self.occupy_mapping.items():
                    # 새로 추가하신 헬퍼 함수로 0 또는 1 추출
                    current_device_val = await self.ant.read_device_io_value(device_name)
                    
                    # 통신 실패 등으로 None이 온 경우는 스킵
                    if current_device_val is None:
                        continue
                    
                    # 정수형태(0/1)로 정제
                    current_device_val = int(current_device_val)
                    
                    # 상태가 변경되었을 때만 PLC에 쓰기 수행
                    if (self.last_occupy_device_states[device_name] is None) or (current_device_val != self.last_occupy_device_states[device_name]):
                        logger.info(f"🚨 디바이스 점유 상태 변경 감지 ({device_name}): {self.last_occupy_device_states[device_name]} -> {current_device_val}")
                        
                        # 기존에 만들어두신 비동기 단건 쓰기 함수 사용
                        # 예: await self._write_register_async(target_reg, current_device_val)
                        await self._write_register_async(target_reg, current_device_val)
                        
                        # 최근 상태 갱신
                        self.last_occupy_device_states[device_name] = current_device_val
            except Exception as e:
                logger.error(f"디바이스 점유 상태 모니터링 루프 에러: {e}")
            
            # 요구사항: 폴링 주기 1초
            await asyncio.sleep(1.0)
        
    async def monitor_vehicle_pause(self):
        '''
        [task] PLC HR 58번 감시 차량 일시정지(1) 및 재개(0)를 제어
        '''
        logger.info(f'PLC 차량 제어 감시 루프(HR 58) -> Pause/Resume 동기화 시작')
        while True:
            try:
                # 클라이언트 연결 상태 체크
                if self.connected and self.client is not None:
                    # 58번 레지스터 단건 읽기 (혹은 락이 필요하다면 async with self.modbus_lock: 사용)
                    response = self.client.read_holding_registers(address=58, count=1)
                    
                    if response and not response.isError():
                        current_plc_val = response.registers[0] # 0 또는 1
                        
                        # 상태가 변경되었을 때만 처리 (최초 1회 실행 포함)
                        if (self.last_pause_plc_state is None) or (current_plc_val != self.last_pause_plc_state):
                            
                            if current_plc_val == 1:
                                logger.warning(f"🚨 PLC HR 58 제동 신호 감지 (1) -> Forklift 일시정지(Pause) 명령 송신")
                                res = await self.ant.pause_vehicle()
                                logger.info(f"Pause API 결과: {res}")
                                
                            elif current_plc_val == 0:
                                # 최초 구동 시(None -> 0) 플래그 일치만을 위한 불필요한 resume 호출 방어
                                if self.last_pause_plc_state is not None:
                                    logger.info(f"▶ PLC HR 58 제동 해제 감지 (0) -> Forklift 이동 재개(Resume) 명령 송신")
                                    res = await self.ant.resume_vehicle()
                                    logger.info(f"Resume API 결과: {res}")
                                else:
                                    logger.info("초기 가동 상태 58번=0 확인 (대기)")

                            # 최근 상태 갱신
                            self.last_pause_plc_state = current_plc_val

            except Exception as e:
                logger.error(f"차량 Pause/Resume 모니터링 루프 에러: {e}")
                
            await asyncio.sleep(0.5) # 0.5초 주기로 폴링