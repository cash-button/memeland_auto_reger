import asyncio
from time import sleep
from copy import deepcopy
from random import randint, choice
from sys import platform
import requests

import aiohttp
import aiofiles
import better_automation.twitter.api
import better_automation.twitter.errors
from better_automation import TwitterAPI
from better_proxy import Proxy

import config
from core import SolveCaptcha
from utils import get_connector, logger

if platform == "windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class StartSubs:
    def __init__(self,
                 account_data: dict):
        self.twitter_client: better_automation.twitter.api.TwitterAPI | None = None

        account_data['window_name'].update_accs()
        self.target_account_token: str = account_data['target_account_token']
        self.account_list: list = account_data['accounts_list']
        self.proxies_list = account_data['proxies_list']
        self.subs_count: int = account_data['subs_count']

        self.current_account_proxy: str | None = None

        if self.target_account_token in self.account_list:
            self.account_list.remove(self.target_account_token)

    async def get_account_username(self) -> str:
        while True:
            try:
                account_username: str = await self.twitter_client.request_username()

            except better_automation.twitter.errors.Forbidden as error:
                if 326 in error.api_codes:
                    logger.info(f'{self.target_account_token} | Обнаружена капча на аккаунте, пробую решить')

                    SolveCaptcha(auth_token=self.twitter_client.auth_token,
                                 ct0=self.twitter_client.ct0).solve_captcha(
                        proxy=Proxy.from_str(
                            proxy=self.current_account_proxy).as_url if self.current_account_proxy else None)
                    continue

                raise better_automation.twitter.errors.Forbidden(error.response)

            else:
                return account_username


    async def get_subscribers_count(self, username: str) -> int:
        while True:
            try:
                user_id = await self.twitter_client.request_user_id(username)
                followers = len(await self.twitter_client.request_followers(user_id, count=self.subs_count))
                return followers

            except better_automation.twitter.errors.Forbidden as error:
                if 326 in error.api_codes:
                    logger.info(f'{self.target_account_token} | Обнаружена капча на аккаунте, пробую решить')

                    SolveCaptcha(auth_token=self.twitter_client.auth_token,
                                 ct0=self.twitter_client.ct0).solve_captcha(
                        proxy=Proxy.from_str(
                            proxy=self.current_account_proxy).as_url if self.current_account_proxy else None)
                    continue

                raise better_automation.twitter.errors.Forbidden(error.response)

    async def subscribe_account(self,
                                target_username: str,
                                subs_count: int) -> None:
        i: int = subs_count
        local_accounts_list: list = deepcopy(self.account_list)

        while i < self.subs_count:
            if not local_accounts_list:
                logger.error(f'{self.target_account_token} | Аккаунты закончились')
                return

            random_token: None = None

            try:
                random_token: str = local_accounts_list.pop(randint(0, len(local_accounts_list) - 1))
                temp_twitter_proxy: str | None = next(self.proxies_list) if self.proxies_list else None

                async with aiohttp.ClientSession(
                        connector=await get_connector(
                            proxy=temp_twitter_proxy if temp_twitter_proxy else await get_connector(
                                proxy=None))) as aiohttp_twitter_session:

                    temp_twitter_client: better_automation.twitter.api.TwitterAPI = TwitterAPI(
                        session=aiohttp_twitter_session,
                        auth_token=random_token)

                    if config.CHANGE_PROXY_URL:
                        async with aiohttp.ClientSession() as change_proxy_session:
                            async with change_proxy_session.get(url=config.CHANGE_PROXY_URL) as r:
                                logger.info(
                                    f'{temp_twitter_client.auth_token} | Успешно сменил Proxy, статус: {r.status}')

                        if config.SLEEP_AFTER_PROXY_CHANGING:
                            logger.info(f'{temp_twitter_client.auth_token} | Сплю {config.SLEEP_AFTER_PROXY_CHANGING} '
                                        f'сек. после смены Proxy')
                            await asyncio.sleep(delay=config.SLEEP_AFTER_PROXY_CHANGING)

                    if not self.twitter_client.ct0:
                        self.twitter_client.set_ct0(await self.twitter_client._request_ct0())

                    while True:
                        try:
                            await temp_twitter_client.follow(
                                user_id=await temp_twitter_client.request_user_id(username=target_username))

                        except better_automation.twitter.errors.Forbidden as error:
                            if 326 in error.api_codes:
                                logger.info(
                                    f'{self.target_account_token} | Обнаружена капча на аккаунте, пробую решить')

                                SolveCaptcha(auth_token=temp_twitter_client.auth_token,
                                             ct0=temp_twitter_client.ct0).solve_captcha(
                                    proxy=Proxy.from_str(
                                        proxy=temp_twitter_proxy).as_url if temp_twitter_proxy else None)
                                continue

                            raise better_automation.twitter.errors.Forbidden(error.response)

                        except KeyError as error:
                            if error.args[0] in ['rest_id',
                                                 'user_result_by_screen_name']:
                                logger.error(f'{temp_twitter_client.auth_token} | Не удалось найти пользователя '
                                             f'{target_username}')
                                return

                            else:
                                logger.error(f'{temp_twitter_client.auth_token} | Не удалось подписаться на '
                                             f'{target_username}: {error}')
                                if 'Too Many Requests' in str(error): sleep(10)
                                elif 'this account is temporarily locked' in str(error): return False
                                elif 'Unauthorized' in str(error): return False

                        except Exception as error:
                            logger.error(f'{temp_twitter_client.auth_token} | Не удалось подписаться на '
                                         f'{target_username}: {error}')
                            if 'Too Many Requests' in str(error): sleep(10)
                            elif 'this account is temporarily locked' in str(error): return False
                            elif 'Unauthorized' in str(error): return False

                        else:
                            logger.success(
                                f'{temp_twitter_client.auth_token} | Успешно подписался на {target_username} '
                                f'| {i + 1}/{self.subs_count}')
                            i += 1
                            break
                    sleep(randint(5, 15))

            except Exception as error:
                logger.error(f'{random_token} | Неизвестная ошибка при подписке на {target_username}: {error} ')

        async with aiofiles.open('result/twitter_success_subs.txt', 'a', encoding='utf-8-sig') as f:
            await f.write(f'{self.twitter_client.auth_token}:{target_username}\n')

        # logger.debug(f'')
        sleep(randint(10, 15))

    async def start_subs(self):
        self.current_account_proxy: str | None = next(self.proxies_list) if self.proxies_list else None

        async with aiohttp.ClientSession(
                connector=await get_connector(
                    proxy=self.current_account_proxy) if self.current_account_proxy else await get_connector(
                    proxy=None)) as aiohttp_twitter_session:
            self.twitter_client: better_automation.twitter.api.TwitterAPI = TwitterAPI(
                session=aiohttp_twitter_session,
                auth_token=self.target_account_token)

            if not self.twitter_client.ct0:
                self.twitter_client.set_ct0(await self.twitter_client._request_ct0())

            account_username: str = await self.get_account_username()
            subs_count = await self.get_subscribers_count(username=account_username)
            if subs_count >= self.subs_count:
                logger.success(f'{account_username} уже имеет {self.subs_count}+ подписчиков!')
                async with aiofiles.open('result/twitter_success_subs.txt', 'a', encoding='utf-8-sig') as f:
                    await f.write(f'{self.twitter_client.auth_token}:{account_username}\n')
                return True

        await self.subscribe_account(target_username=account_username, subs_count=subs_count)


class StartGms:
    def __init__(self,
                 account_data: dict):
        self.twitter_client: better_automation.twitter.api.TwitterAPI | None = None

        account_data['window_name'].update_accs()
        self.account_token: str = account_data['account_token']
        self.account_proxy = account_data['account_proxy']


    async def get_account_username(self) -> str:
        while True:
            try:
                account_username: str = await self.twitter_client.request_username()

            except better_automation.twitter.errors.Forbidden as error:
                if 326 in error.api_codes:
                    logger.info(f'{self.account_token} | Обнаружена капча на аккаунте, пробую решить')

                    SolveCaptcha(auth_token=self.twitter_client.auth_token,
                                 ct0=self.twitter_client.ct0).solve_captcha(
                        proxy=Proxy.from_str(
                            proxy=self.account_proxy).as_url if self.account_proxy else None)
                    continue

                raise better_automation.twitter.errors.Forbidden(error.response)

            else:
                return account_username

    async def send_reply(self):
        while True:
            try:
                gm_response = await self.twitter_client.reply(tweet_id='1718788079413244315', text=choice(['GM', 'Gm', 'gm']))
            except better_automation.twitter.errors.Forbidden as error:
                if 326 in error.api_codes:
                    logger.info(f'{self.account_token} | Обнаружена капча на аккаунте, пробую решить')

                    SolveCaptcha(auth_token=self.twitter_client.auth_token,
                                 ct0=self.twitter_client.ct0).solve_captcha(
                        proxy=Proxy.from_str(
                            proxy=self.account_proxy).as_url if self.account_proxy else None)
                    continue

                raise better_automation.twitter.errors.HTTP(error.response)

            except better_automation.twitter.errors.HTTPException as error:
                if 187 in error.api_codes:
                    logger.success(f'{self.account_token} | Пост с GM уже сделан!')
                    return 'already_did_post'

                raise better_automation.twitter.errors.Forbidden(error.response)

            else:
                return gm_response

    async def start_gms(self):
        async with aiohttp.ClientSession(
                connector=await get_connector(
                    proxy=self.account_proxy) if self.account_proxy else await get_connector(
                    proxy=None)) as aiohttp_twitter_session:

            self.twitter_client: better_automation.twitter.api.TwitterAPI = TwitterAPI(
                session=aiohttp_twitter_session,
                auth_token=self.account_token)

            if not self.twitter_client.ct0:
                self.twitter_client.set_ct0(await self.twitter_client._request_ct0())

            gm_response = await self.send_reply()
            if gm_response.isdigit():
                twitter_name = await self.get_account_username()
                twitter_link = f'https://twitter.com/{twitter_name}/status/{gm_response}'
                logger.success(f'{self.account_token} | Удачно написал GM в твиттер!')
            else:
                twitter_link = gm_response

            async with aiofiles.open('result/success_gms.txt', 'a', encoding='utf-8-sig') as f:
                await f.write(f'{self.twitter_client.auth_token}:{twitter_link}\n')

            if gm_response != 'already_did_post':
                sleep(randint(5, 20))
            return True



def start_subs(account_data: dict) -> None:
    try:
        asyncio.run(StartSubs(account_data=account_data).start_subs())

    except Exception as error:
        logger.error(f'{account_data["target_account_token"]} | Неизвестная ошибка при обработке аккаунта: {error}')


def start_gms(account_data: dict) -> None:
    try:
        if config.CHANGE_PROXY_URL:
            r = requests.get(config.CHANGE_PROXY_URL)
            logger.info(f'{account_data["account_token"]} | Успешно сменил Proxy, статус: {r.status_code}')

            if config.SLEEP_AFTER_PROXY_CHANGING:
                logger.info(
                    f'{account_data["account_token"]} | Сплю {config.SLEEP_AFTER_PROXY_CHANGING} сек. после смены Proxy')
                sleep(config.SLEEP_AFTER_PROXY_CHANGING)

        asyncio.run(StartGms(account_data=account_data).start_gms())

    except Exception as error:
        logger.error(f'{account_data["account_token"]} | Неизвестная ошибка при обработке аккаунта: {error}')
