import aiohttp
import logging
import asyncio

logger = logging.getLogger(__name__)

class AntApiBase:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _get(self, api_version: str, token: str, endpoint: str, params=None, headers=None):
        session = await self._get_session()
        url = f"{self.base_url}/{api_version}/{endpoint}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with session.get(url, headers=headers, params=params, ssl=False) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as e:
            print(f"[GET 오류] {url} → {e}")
            return None

    async def _post(self, api_version: str, token: str, endpoint: str,
                    json_data=None, params=None, headers=None):
        url = f"{self.base_url}/{api_version}/{endpoint}"
        _headers = {"Authorization": f"Bearer {token}"}
        if headers:
            _headers.update(headers)

        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url, headers=_headers, json=json_data,
                        params=params, ssl=False,
                        timeout=aiohttp.ClientTimeout(total=10)                        
                    ) as resp:
                        if resp.status in (200, 201):
                            return await resp.json()
                        else:
                            text = await resp.text()
                            logger.error(f"[POST {resp.status}] {url} → {text}")
                            return None
            except Exception as e:
                logger.error(f"[POST 오류 시도{attempt+1}/2] {url} → {e}")
                if attempt ==0:
                    await asyncio.sleep(0.5)
                    continue
                return None

    async def _delete(self, api_version: str, token: str, endpoint: str, 
                      params=None, headers=None):
        session = await self._get_session()
        url = f"{self.base_url}/{api_version}/{endpoint}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with session.delete(url, headers=headers,
                                      params=params, ssl=False) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as e:
            print(f"[DELETE 오류] {url} → {e}")
            return None

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None