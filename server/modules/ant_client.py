import logging, time
from modules.ant_api_base import AntApiBase

logger = logging.getLogger(__name__)


class AntClient(AntApiBase):
    def __init__(self, base_url: str):
        super().__init__(base_url)
        self.token       = None
        self.api_version = None
        self.connected   = False

    # ── 로그인 ──────────────────────────────────────────
    async def login(self, username: str, password: str,
                    is_ldap=False, major=0, minor=2):
        """
        매뉴얼 G 1.1.3.1 POST login 방식
        POST /wms/rest/login
        """
        session = await self._get_session()
        url     = f"{self.base_url}/login"
        payload = {
            "username"  : username,
            "password"  : password,
            "isLdap"    : is_ldap,
            "apiVersion": {"major": major, "minor": minor},
        }
        try:
            async with session.post(url, json=payload, ssl=False) as resp:
                resp.raise_for_status()
                data             = await resp.json()
                self.token       = data["token"]
                self.api_version = data["apiVersion"]
                self.connected   = True
                logger.info(f"ANT server 로그인 성공 / API: {self.api_version}")
                return self.token, self.api_version
        except Exception as e:
            self.connected  = False
            self.token      = None
            logger.error(f"로그인 실패: {e}")
            return None, None
        
    def is_ready(self) -> bool:
        return self.connected and self.token is not None

    # ── 애플리케이션 정보 ────────────────────────────────
    async def get_application_info(self):
        return await self._get(self.api_version, self.token, "application")

    # ── 서버 정보 ────────────────────────────────────────
    async def get_server_info(self):
        return await self._get(self.api_version, self.token, "server")

    # ── 차량 목록 ────────────────────────────────────────
    async def get_vehicles(self):
        # result = await self._get(self.api_version, self.token, "vehicles", headers={"Authorization" : f"Bearer {self.token}"})
        result = await self._get(self.api_version, self.token, "vehicles")
        if result is None:
            return []
        return result.get("payload", {}).get("vehicles", [])
    
    # ── 미션 모두 취소 ────────────────────────────────────────
    async def cancel_missions(self):
        result = await self._delete(self.api_version, self.token, "missions")
        logger.info(f'ANT 서버 응답 결과: {result}')
        if result is None:
            return []
        return result.get("payload", {}).get("cancelled", [])
    
    # ── 단일 미션 취소 ────────────────────────────────────────
    async def cancel_mission(self, mission_id):
        result = await self._delete(self.api_version, self.token, f'missions/{mission_id}')
        logger.info(f'ANT 서버 응답 결과 (미션 취소 {mission_id}) : {result}')
        if result is None:
            return None
        return result.get('payload', {}).get('missionid', {})
    
    # ── 미션 정보 ────────────────────────────────────────
    async def get_mission(self, mission_id):
        """비동기 버전 지정 모드로 특정 미션 정보를 가져옵니다."""
        endpoint = f"missions/{mission_id}"
        result = await self._get(self.api_version, self.token, endpoint)
        return result.get("payload", {}).get("missions", [])


    # 클래스 내부의 get_missions 함수를 아래와 같이 수정하세요
    async def get_missions(self, order_by=None, data_range=None):
        """가이드 형식에 맞춰 모든 미션 정보를 가져옵니다."""
        endpoint = "missions"
        headers = {"Authorization": f"Bearer {self.token}"}
    
        # 1. 기본 파라미터 설정 (캐시 방지용 타임스탬프)
        params = {"_": int(time.time() * 1000)}

        # 2. 정렬 조건 처리 (가이드 코드 로직 적용)
        if order_by:
            order_clauses = []
            if isinstance(order_by, list):
                for item in order_by:
                    if isinstance(item, list) and len(item) == 2:
                        field, order = item
                        order_clauses.append(f'["{field}","{order.lower()}"]')
                if order_clauses:
                    params["dataorderby"] = f"[{','.join(order_clauses)}]"
            elif isinstance(order_by, str):
                params["dataorderby"] = f'[["{order_by}","asc"]]'

        # 3. 데이터 범위 처리 (예: [0, 100])
        if data_range and isinstance(data_range, list) and len(data_range) == 2:
            params["datarange"] = f"[{data_range[0]},{data_range[1]}]"
            
        
        # API 요청 실행
        result = await self._get(self.api_version, self.token, endpoint, params=params, headers=headers)
    
        if result is None:
            return []
        
        # 결과값에서 미션 리스트 추출
        return result.get("payload", {}).get("missions", [])

    # ── 미션 생성 ────────────────────────────────────────
    async def create_mission(self, mission_data):

        headers = {"Content-Type": "application/json"}
        return await self._post(self.api_version, self.token, "missions", json_data=mission_data, headers=headers)
    

    # ── 알람 목록 ────────────────────────────────────────
    async def get_alarms(self, params=None):
        query_params = {}
        if params and isinstance(params, list):
            query_params = {"fields": ",".join(params)}
            
        result = await self._get(self.api_version, self.token, "alarms", params=query_params)
        if result is None:
            return []
        return result.get("payload", {}).get("alarms", [])

    # ── device 출력 쓰기 ────────────────────────────────────────
    async def write_device(self, device_name: str, value):
        """
        POST /devices/<device_name>/command
        Output 타입 디바이스에 값을 씁니다.
        value: 0/1 또는 "0"/"1"
        """
        body = {
            "command": {
                "name": "write",
                "args": {"value": value},
            }
        }
        endpoint = f"devices/{device_name}/command"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        return await self._post(self.api_version, self.token, endpoint, json_data=body, headers=headers)
    
    
    # ── 디바이스 단건 조회 (G 1.1.24) ───────────────────
    async def get_device(self, device_name: str):
        """
        GET /devices/<device_name>
        디바이스 1개의 상태 정보를 가져옵니다.
        반환: dict (payload 안의 device 정보) 또는 None
        """
        endpoint = f"devices/{device_name}"
        result = await self._get(self.api_version, self.token, endpoint)
        if result is None:
            return None
        return result.get("payload", {}).get('devices', {})
    

   # ── 디바이스 IO 현재값 읽기 헬퍼 ────────────────────
    async def read_device_io_value(self, device_name: str):
        """
        디바이스의 IO 값(0/1)을 추출해서 반환합니다.
        디바이스를 찾지 못하거나 통신 실패 시 None 반환.
        """
        device_data = await self.get_device(device_name)
        if device_data is None:
            return None
        try:
            # 💡 만약 get_device가 리스트 형태나 payload 통째로 반환할 경우를 대비한 안전장치
            if isinstance(device_data, dict) and "payload" in device_data:
                devices_list = device_data.get("payload", {}).get("devices", [])
                device = devices_list[0] if devices_list else {}
            elif isinstance(device_data, list) and len(device_data) > 0:
                device = device_data[0]
            else:
                device = device_data

            # 매뉴얼 G 1.1.23/24 응답 구조 기준
            # payload -> meta -> state -> state -> value
            state = device.get("meta", {}).get("state", {}).get("state", {})
            return state.get("value")
        except (AttributeError, TypeError):
            return None  
        
    
    # ── 차량 일시정지 ────────────────────
    async def pause_vehicle(self):
        body = {
            'command': {
                'name': 'pause'
            }
        }
        endpoint = f'vehicles/Forklift3.3m/command'
        headers = {"Content-Type": "application/json"}
        return await self._post(self.api_version, self.token, endpoint, json_data=body, headers=headers)
    
    # ── 차량 재개 ─────────────────────────────────────────
    async def resume_vehicle(self):
        body = {
            "command": {
                "name": "resume"
            }
        }
        endpoint = f"vehicles/Forklift3.3m/command"
        headers = {"Content-Type": "application/json"}
        return await self._post(self.api_version, self.token, endpoint, json_data=body, headers=headers)
    
    # ── 미션커맨드 취소 ────────────────────────────────────────
    async def ask_mission_cancellation(self, missionid):
        body = {
            "command": {
                "name": "monitorMissionCancellation",
                "args": {
                "askCancel": True
                }
            }
        }
        endpoint = f'missioncommands/{missionid}/command'
        headers = {"Content-Type": "application/json"}
        return await self._post(self.api_version, self.token, endpoint, json_data=body, headers=headers)
    
    # ── 강제 insert ────────────────────────────────
    async def force_insertion(self):
        body = {
            "command": {
                "name": "insert",
                "args": {
                "nodeId": "Parking",
                "forceInsertion": True
                }
            }
        }
        endpoint = f'vehicles/Forklift3.3m/command'
        headers = {"Content-Type": "application/json"}
        return await self._post(self.api_version, self.token, endpoint, json_data=body, headers=headers)
    
    # ── 맵 데이터 ────────────────────────────────
    async def get_map_data(self, level_id: int = 1):
        endpoint = f'maps/level/{level_id}/data'
        result = await self._get(self.api_version, self.token, endpoint)
        if result is None:
            return None
        return result.get("payload", {}).get("data", [])