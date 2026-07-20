import sys, os
import logging
import uvicorn
import asyncio
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
import json
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from modules.mission_monitor import MissionMonitor
from modules.ant_client import AntClient
from modules.ant_connector import AntConnector
from modules.ws_manager import WebSocketManager
from modules.modbus_poller import ModbusPoller
from modules.db import LogDB
from logging.handlers import TimedRotatingFileHandler

# PyInstaller 경로
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 로그를 파일로 저장 (실행파일 디버깅용)
log_path = os.path.join(BASE_DIR, "startup.log")
# 💡 매일 자정에 로그를 로테이팅하는 핸들러 설정
file_handler = TimedRotatingFileHandler(
    filename=log_path,
    when="midnight",      # 매일 자정(00:00)에 로테이션 실행
    interval=1,           # 1일 주기로
    encoding="utf-8",
    backupCount=30        # (옵션) 최대 30일치만 보관하고 옛날 로그는 자동 삭제 (서버 용량 방어)
)

# 💡 파일 이름 형식을 'startup.log_2026-07-06' 형태로 날짜가 붙게 지정
file_handler.suffix = "%Y-%m-%d"

# map cache 변수 (프로그램 시작시 처음 한번만 저장.)
_map_cache = None

# 스트림 핸들러 (콘솔 출력용)
stream_handler = logging.StreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        file_handler,    # 💡 교체된 파일 핸들러 반영
        stream_handler,
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"BASE_DIR: {BASE_DIR}")
logger.info("서버 시작 시도...")


CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
logger.info(f"config 경로: {CONFIG_PATH}")
logger.info(f"config 존재여부: {os.path.exists(CONFIG_PATH)}")

with open(CONFIG_PATH, encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
logger.info("config 로드완료")

db = LogDB(os.path.join(BASE_DIR, "logs.db"))
logger.info("DB 초기화...")

# ── 글로벌 및 싱글턴 초기화 ─────────────────────────────
# ant와 ant_connected는 lifespan에서 초기화됨
poller: ModbusPoller | None = None
ws_manager = WebSocketManager()


# ANT client 초기화 (연결은 나중에)
if cfg["ant_server"].get("mock", False):
    from modules.ant_client_mock import AntClient as MockClient
    ant = MockClient(cfg["ant_server"]["host"])
else:
    base_url = (
        f"http://{cfg['ant_server']['host']}"
        f":{cfg['ant_server']['port']}/wms/rest"
    )
    ant = AntClient(base_url)
    logger.info("ANT client 생성완료")

# ── 연결 상태 전역 관리 ────────────────────────────────
logger.info("connection_status 초기화...")
connection_status = {
    "plc"     : False,
    "ant"     : False,
    "plc_host": "",
    "ant_host": "",
}


# ── ANT 상태 변경 콜백 ─────────────────────────────────
async def on_ant_status_change(connected: bool):
    connection_status["ant"] = connected
    await ws_manager.broadcast({
        "type"  : "connection_status",
        "status": connection_status.copy(),
    })
    logger.info(f"ANT server 상태: {'연결됨' if connected else '끊김'}")


# ── PLC 상태 변경 콜백 ─────────────────────────────────
async def on_plc_status_change(connected: bool):
    connection_status["plc"] = connected
    await ws_manager.broadcast({
        "type"  : "connection_status",
        "status": connection_status.copy(),
    })
    logger.info(f"PLC 상태 변경: {'연결됨' if connected else '끊김'}")

# ── PLC 트리거 콜백 ────────────────────────────────────
# on_plc_trigger 수정 - ACK + DB 추적 추가
async def on_plc_trigger(signal: dict):
    if not ant.is_ready():
        await ws_manager.broadcast({
            "type"   : "error",
            "message": "ANT server 미연결 - 미션 생성 불가",
        })
        return False # 실패 리턴

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
        result = await ant.create_mission(mission_data=mission_data)
        logger.info(f"전송할 미션 데이터 상세:\n{json.dumps(mission_data, indent=4, ensure_ascii=False)}")

        accepted   = result.get("payload", {}).get("acceptedmissions", [])
        mission_id = accepted[0] if accepted else None

        if mission_id:
            # DB에 추적 시작
            db.track_mission(mission_id, signal)
            db.insert(signal, result)

            # # PLC에 ACK ON (미션 수신 확인)
            # ack_coil = signal.get("ack_coil_address")
            # if ack_coil is not None and poller:
            #     poller.write_ack(ack_coil, True)

            await ws_manager.broadcast({
                "type"      : "mission_created",
                "mission_id": mission_id,
                "signal"    : signal,
                "result"    : result,
            })
            logger.info(f"미션 생성 + 추적 시작: {mission_id}")

            battery_variable = 0

            try:
                vehicle_data = await ant.get_vehicles()
                if isinstance(vehicle_data, list):
                    vehicle_data = vehicle_data[0]
                    battery_info = vehicle_data.get('state', {}).get('battery.info', ["0", "0"])
                    logger.info(f'------------------------{battery_info}')
                    battery = int(float(battery_info[0]))
                    logger.info(f'배터리 잔량 {battery}%')

                    if battery >=75:
                        battery_variable = 2
                        logger.info(f'✅ 배터리가 75% 이상입니다. 충전 x')
                    else:
                        battery_variable = 1
                        logger.info(f'⚠️ 배터리가 75% 미만입니다. 충전 o')
                else:
                    logger.warning(f'⚠️ 차량 데이터를 불러올 수 없어 기본 배터리 변수(0)를 적용합니다.')
            except Exception as b_err:
                logger.error(f"❌ 배터리 조회 중 에러 발생: {b_err}, 기본 변수(0) 적용")

            mission_data = {
                "missionrequest": {
                    "requestor": "admin",
                    "missiontype": 8,
                    "tonode": 'Parking',
                    "cardinality": 1,
                    "priority": 1,
                    "deadline" : None,
                    "parameters": {
                        "desc": "Mission extension",
                        "type": "org.json.JSONObject",
                        "name": "parameters",
                        "value": {
                            "payload": "Default Payload",
                            "dynamicnodetypes" : {
                                "tonodetype" : {
                                    "name" : "Parking",
                                    "vars" : {
                                        'charge' : battery_variable,
                                    }
                                }
                            }

                        }
                    }
                }
            }           

            result2 = await ant.create_mission(mission_data=mission_data)
            logger.info(f'parking 미션 생성완료 {result2}')

        else:
            logger.error(f"미션 생성 실패: {result}")
            await ws_manager.broadcast({
                "type"   : "error",
                "message": f"미션 생성 실패: {result}",
            })

    except Exception as e:
        logger.error(f"on_plc_trigger 예외: {e}")

# 대기 미션이 있으면 현재 미션에 취소 요청
async def node_monitor_loop(trigger_node: str, interval: float = 2.0):
    """
    차량이 trigger_node에 도달하고 대기 미션이 있으면
    현재 미션에 취소 요청을 보냅니다.
    매뉴얼 G 1.1.14 monitorMissionCancellation 사용.
    """
    if not trigger_node:
        logger.info("❌ cancellation_trigger_node 미설정 - 노드 모니터 비활성")
        return

    # navigationstate 값 (매뉴얼 G 1.1.8)
    NAV_PLANNED = '1'

    while True:
        await asyncio.sleep(interval)

        if not ant.is_ready():
            continue

        try:
            # 1. 차량 현재 노드 확인
            vehicles_data = await ant.get_vehicles()
            if not vehicles_data:
                continue

            vehicles_data       = vehicles_data[0]
            location = vehicles_data.get('location', {})
            current_node  = location.get('currentnodeid')
            running_mission = vehicles_data.get("missionid")
            logger.info(f'현재 노드 위치 : {current_node}')

            if current_node is None or str(current_node).strip() != str(trigger_node).strip():
                continue

            logger.info(f"🎯 [노드 매칭 성공] 차량이 목표 노드 {trigger_node}에 도달했습니다!")

            if not running_mission:
                logger.warning(f"⚠️ 트리거 노드에는 도달했으나, 차량에 할당된 실행 중인 미션 ID가 없습니다. (missionid: {running_mission})")
                continue

            logger.info(f"트리거 노드 도달: {trigger_node}, 실행중 미션: {running_mission}")


            # 2. 대기중(planned) 미션 존재 확인
            missions = await ant.get_missions(order_by=[["createdat", "desc"]], data_range=[10])

            for m in missions:
                logger.info(f"ID: {m.get('missionid')}, NavState: {m.get('navigationstate')}, Assigned: {m.get('assignedto')}")

            planned  = [
                m for m in missions
                if str(m.get("navigationstate")) == NAV_PLANNED
            ]

            if not planned:
                logger.info("ℹ️ 트리거 노드에 도달했고 실행 중인 미션이 있으나, 뒤에 대기 중인(Planned) 미션이 없어 취소하지 않습니다.")
                continue

            logger.info(
                f"대기 미션 {len(planned)}개 확인 → "
                f"미션 {running_mission} 취소 요청"
            )

            # 3. 현재 미션 취소 요청 (매뉴얼 G 1.1.14)
            result = await ant.ask_mission_cancellation(running_mission)
            if result is None:
                logger.error("미션 취소 요청 실패")
            else:
                logger.info(f"미션 취소 요청 완료: {result}")
                await ws_manager.broadcast({
                    "type"      : "mission_cancel_requested",
                    "mission_id": running_mission,
                    "reason"    : f"노드 {trigger_node} 도달 + 대기 미션 {len(planned)}개",
                })

        except Exception as e:
            logger.error(f"노드 모니터 예외: {e}")

# ── 앱 수명주기 ────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ant, poller

    # PLC 폴러 시작
    poller = ModbusPoller(
        host             = cfg["plc"]["host"],
        ant_client       = ant,
        port             = cfg["plc"]["port"],
        signal_map       = cfg["signal_map"],
        on_trigger       = on_plc_trigger,
        on_status_change = on_plc_status_change,
    )
    asyncio.create_task(poller.start(cfg["plc"]["poll_interval"]))
    connection_status["plc_host"] = cfg["plc"]["host"]
    connection_status["ant_host"] = cfg["ant_server"]["host"]

    # ANT 커넥터 (자동 재연결)
    if not cfg["ant_server"].get("mock", False):
        connector = AntConnector(
            ant_client        = ant,
            username          = cfg["ant_server"]["username"],
            password          = cfg["ant_server"]["password"],
            on_status_change  = on_ant_status_change,
            retry_interval    = 10,   # 10초마다 재시도
        )
        asyncio.create_task(connector.start())
    else:
        # mock 모드는 항상 연결된 것으로 처리
        ant.connected            = True
        connection_status["ant"] = True


    monitor = MissionMonitor(
        ant        = ant,
        db         = db,
        ws_manager = ws_manager,
        plc_poller = poller,
        signal_map = cfg["signal_map"],
    )
    asyncio.create_task(monitor.start(interval=5.0))

    logger.info(f"🔍 로드된 취소 트리거 노드: {cfg.get("cancellation_trigger_node")}")
    asyncio.create_task(
        node_monitor_loop(
        trigger_node = cfg.get("cancellation_trigger_node"),
        interval     = 1.0,
        )
    )

    logger.info("서버 시작 완료 - PLC/ANT 연결 시도 중...")
    yield

    # 종료 시 세션 정리
    if ant:
        await ant.close()

app = FastAPI(lifespan=lifespan)
logger.info("FastAPI 앱 생성 완료")

# ── API ────────────────────────────────────────────────
@app.get("/api/alarms")
async def alarms():
    if not ant.is_ready():
        return []
    try:
        return await ant.get_alarms()
    except Exception as e:
        logger.error(f"알람조회 실패: {e}")
        return []

@app.get("/api/tracking")
def tracking():
    return db.get_tracking_all()

@app.get("/api/status")
def status():
    return connection_status

@app.get("/api/vehicles")
async def vehicles():
    if not ant.is_ready():
        return []
    try:
        return await ant.get_vehicles()
    except Exception as e:
        logger.error(f"차량 조회 실패: {e}")
        return []
    
@app.post("/api/missions/cancel-all")
async def cancel_missions():
    if not ant.is_ready():
        return []
    try:
        return await ant.cancel_missions()
    except Exception as e:
        logger.error(f"미션 취소 실패: {e}")
        return []
    
@app.post("/api/missions/create")
async def create_mission():
    try:
        mission_cfg = cfg.get("mission_ex1", {})
        if not mission_cfg:
            raise ValueError("config.yaml에서 mission_ex1 설정을 찾을 수 없습니다.")

        mission_data = {
            "missionrequest": {
                "requestor": "admin",
                "missiontype": 7,
                "fromnode": mission_cfg.get("fromnode"),
                "tonode": mission_cfg.get("tonode"),
                "cardinality": 1,
                "priority": 2,
                "deadline" : None,
                "parameters": {
                    "desc": "Mission extension",
                    "type": "org.json.JSONObject",
                    "name": "parameters",
                    "value": {
                        "vehicle": "Forklift3.3m",
                        "payload": "Default Payload",
                        "dynamicnodetypes" : {
                            "fromnodetype" : {
                                "name" : "Pick",
                                "vars" : {
                                    'height1' : mission_cfg.get("fromh1"),
                                    'height2' : mission_cfg.get("fromh2")
                                }
                            },
                            "tonodetype" : {
                                "name" : "Drop",
                                "vars" : {
                                    'height1' : mission_cfg.get("toh1"),
                                    'height2' : mission_cfg.get("toh2")
                                }
                            }
                        }

                    }
                }
            }
        }
        logger.info(f"전송할 미션 데이터 상세:\n{json.dumps(mission_data, indent=4, ensure_ascii=False)}")
        logger.info(f"미션 생성 요청 수신: {mission_cfg.get("fromnode")} -> {mission_cfg.get("tonode")}")

        result = await ant.create_mission(mission_data= mission_data)
        logger.info(f'미션 생성결과: {result}')

        if result:
            return {
                "status": "success",
                "message": "Mission created successfully",
                "payload": result.get("payload")
            }
        else:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Failed to create mission in ANT server"}
            )
    
    except Exception as e:
        logger.error(f"Endpoint Error: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.delete('/api/tracking/{mission_id}')
async def delete_mission_tracking(mission_id:str):
    '''
    오작동 / 잘못 생성된 미션을 삭제.
    1. ANT 서버에 취소 요청
    2. 추적 테이블에서 레코드 삭제 -> 자동 재생성 중단
    '''
    ant_result = None

    if ant.is_ready():
        try:
            ant_result = await ant.cancel_mission(mission_id)
            logger.info(f"미션 {mission_id} ANT 서버 취소 요청 결과: {ant_result}")
        except Exception as e:
            logger.warning(f"미션 {mission_id} ANT 서버 취소 실패 (추적은 계속 중단 처리): {e}")
    else:
        logger.warning(f"ANT server 미연결 - 미션 {mission_id} ANT 취소 생략, 추적만 중단")

    try:
        current_tracking = db.get_tracking_by_id(mission_id)

        if current_tracking and 'signal' in current_tracking:
            signal = current_tracking['signal']
            mission_case = signal.get('mission_case')

            if mission_case is not None:
                logger.info(f'사용자 취소 버튼 감지 -> plc{77 + mission_case}번 완료 펄스 강제 전송')
                # 백그라운드로 폴러 호출
                asyncio.create_task(poller.trigger_mission_clear_pulse(mission_case))
    except Exception as e:
        logger.error(f'취소 미션의 plc 완료 펄스 처리 중 에러 : {e}')

    try:            
        deleted = db.delete_tracking(mission_id)
    except Exception as e:
        logger.error(f"미션 {mission_id} 추적 삭제 실패: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )
    
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={'status': 'error', 'message': f"추적 중인 미션 {mission_id}을 찾을 수 없습니다."}
        )

    await ws_manager.broadcast({
        "type"      : "mission_tracking_deleted",
        "mission_id": mission_id,
    })

    return {
        "status"    : "success",
        "message"   : f"미션 {mission_id} 삭제(추적 중단) 완료",
        "ant_result": ant_result,
    }
        


@app.get("/api/missions")
async def missions():
    if not ant.is_ready():
        return []
    try:
        # 가이드 예시처럼 정렬 조건을 넣고 싶다면 아래와 같이 호출 가능합니다.
        # 예: 생성시간(createdat) 내림차순 정렬
        result = await ant.get_missions(order_by=[["createdat", "desc"]])
        return result
    except Exception as e:
        logger.error(f"미션 조회 실패: {e}")
        return []

@app.get("/api/logs")
def logs():
    return db.get_all()

@app.post("/api/vehicles/forceinsert")
async def force_insert():
    if not ant.is_ready():
        return []
    try:
        result = await ant.force_insertion()
        data = result.get("payload", {}).get("vehicle", {})
        error_list = data.get('state', {}).get('errors', [])
        logger.info(f'-------------------------forceinsert 결과 : {error_list}')
        return error_list
    except Exception as e:
        logger.error(f"forceinsert 실패: {e}")
        return []
    
@app.get('/api/map')
async def get_map(level: int = 1):
    global _map_cache

    if not ant.is_ready():
        return []
    
    try:
        if _map_cache is None:
             data = await ant.get_map_data(level_id=level)
             logger.info(f'---------------------------------map data는 {data}')
             if data:
                 _map_cache = data
                 logger.info(f'레벨 {level} 맵 데이터를 성공적으로 최초 캐싱했습니다.')
        return _map_cache or []
    except Exception as e:
        logger.error(f'맵 데이터 조회 실패: {e}')
        return []



# ── WebSocket ──────────────────────────────────────────
@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws_manager.connect(ws)
    # 연결 즉시 현재 상태 전송
    await ws.send_json({
        "type"  : "connection_status",
        "status": connection_status.copy(),
    })
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


    
# ── 정적 파일 & SPA ────────────────────────────────────
# STATIC = Path("static")

#pyinstaller 실행파일 경로
STATIC = Path(BASE_DIR) / "static"

if STATIC.exists() and (STATIC / "index.html").exists():
    # static 폴더 전체 마운트 (assets, favicon 등 전부 포함)
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
else:
    @app.get("/")
    def root():
        return JSONResponse({
            "message": "React 빌드 파일 없음",
            "hint"   : "ui/ 폴더에서 npm run build 실행 후 재시작하세요.",
            "api"    : "/docs"
        })
    
# 배포시 main 실행
if __name__ == "__main__":
    logger.info("uvicorn 시작...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
    