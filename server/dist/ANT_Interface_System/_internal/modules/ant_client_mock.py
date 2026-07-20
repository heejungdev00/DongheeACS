import random
import logging

logger = logging.getLogger(__name__)

class AntClient:
    def __init__(self, base_url: str):
        self.token       = "mock-token"
        self.api_version = "v0.2"
        logger.info(f"[MOCK] ANT client 초기화: {base_url}")

    async def login(self, username, password, **kwargs):
        return self.token, self.api_version

    async def create_mission(self, fromnode, tonode, payload,
                             priority=2, mission_type=7):
        mission_id = str(random.randint(1000, 9999))
        logger.info(f"[MOCK] 미션 생성: {fromnode} → {tonode} / {payload} → ID {mission_id}")
        return {
            "payload": {
                "acceptedmissions": [mission_id],
                "rejectedmissions": [],
                "pendingmissions" : [],
            },
            "retcode": 0,
        }

    async def get_vehicles(self):
        return [
            {"name": "AGV-001", "operatingstate": 2, "missionid": "1001",
             "state": {"battery.info": ["82"]},
             "location": {"currentnode": {"name": "Node14"}}},
            {"name": "AGV-002", "operatingstate": 1, "missionid": "",
             "state": {"battery.info": ["95"]},
             "location": {"currentnode": {"name": "ChargerNode"}}},
            {"name": "AGV-003", "operatingstate": 4, "missionid": "",
             "state": {"battery.info": ["34"]},
             "location": {"currentnode": {"name": "ChargerNode"}}},
        ]

    async def get_missions(self):
        return [
            {"missionid": "1001", "transportstate": 7,
             "fromnode": "PickNode_A", "tonode": "DropNode_A",
             "payload": "BoxA", "assignedto": "AGV-001"},
            {"missionid": "1002", "transportstate": 1,
             "fromnode": "PickNode_B", "tonode": "StationDrop",
             "payload": "PalletB", "assignedto": ""},
        ]

    async def get_alarms(self):
        return []

    async def close(self):
        pass

    async def get_alarms(self, limit=100):
        return [
            {
                "uuid"        : "abc-001",
                "eventname"   : "vehicle.error.Lost",
                "sourceid"    : "AGV-001",
                "sourcetype"  : "vehicle",
                "state"       : 0,
                "eventcount"  : 3,
                "firsteventat": "2026-05-14T09:10:00+09:00",
                "lasteventat" : "2026-05-14T09:15:00+09:00",
                "alarmmessage": "차량 위치를 잃음",
            },
            {
                "uuid"        : "abc-002",
                "eventname"   : "vehicle.warning.BatteryLow",
                "sourceid"    : "AGV-002",
                "sourcetype"  : "vehicle",
                "state"       : 1,
                "eventcount"  : 1,
                "firsteventat": "2026-05-14T08:00:00+09:00",
                "lasteventat" : "2026-05-14T08:00:00+09:00",
                "alarmmessage": "배터리 부족",
            },
            {
                "uuid"        : "abc-003",
                "eventname"   : "vehicle.critical.NoRangeDataAvailable",
                "sourceid"    : "AGV-003",
                "sourcetype"  : "vehicle",
                "state"       : 2,
                "eventcount"  : 1,
                "firsteventat": "2026-05-14T07:30:00+09:00",
                "lasteventat" : "2026-05-14T07:30:00+09:00",
                "alarmmessage": "레이저 데이터 없음",
            },
        ]