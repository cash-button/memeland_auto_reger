import asyncio
from random import choice
from sys import platform
from time import sleep
from urllib.parse import urlparse, parse_qs

import aiofiles
import aiohttp
import aiohttp.client
import better_automation.twitter.api
import better_automation.twitter.errors
import eth_account.signers.local
import requests
import tls_client.sessions
from better_automation import TwitterAPI
from better_proxy import Proxy
from bs4 import BeautifulSoup
from eth_account.messages import encode_defunct
from web3.auto import w3

import config
from exceptions import Unauthorized, AccountSuspended
from utils import check_empty_value
from utils import format_range
from utils import generate_eth_account, get_account
from utils import get_connector
from utils import logger
from .solve_captcha import SolveCaptcha

if platform in ["windows", "win32"]:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class Reger:
    def __init__(self, source_data: dict) -> None:
        source_data['window_name'].update_accs()
        self.account_token: str = source_data['account_token']
        self.account_proxy: str | None = source_data['account_proxy']
        self.account_private_key: str | None = source_data['account_private_key']
        self.user_action: int = source_data['user_action']

        self.twitter_client: better_automation.twitter.api.TwitterAPI | None = None
        self.meme_client: tls_client.sessions.Session | None = None
        self.account_too_new_attempts: int = 0
        self.account_unauthorized: int = 0


    def get_tasks(self) -> dict:
        r = self.meme_client.get(url='https://memefarm-api.memecoin.org/user/tasks',
                                 headers={
                                     **self.meme_client.headers,
                                     'content-type': None
                                 })

        return r.json()

    def get_info(self) -> dict:
        r = self.meme_client.get(url='https://memefarm-api.memecoin.org/user/info',
                                 headers={
                                     **self.meme_client.headers,
                                     'content-type': None
                                 })

        return r.json()

    def get_twitter_account_names(self) -> tuple[str, str]:
        r = self.meme_client.get(url='https://memefarm-api.memecoin.org/user/info',
                                 headers={
                                     **self.meme_client.headers,
                                     'content-type': None
                                 })

        return r.json()['twitter']['username'], r.json()['twitter']['name']

    def link_wallet_request(self,
                            address: str,
                            sign: str,
                            message: str) -> tuple[bool, str, int]:
        while True:
            r = self.meme_client.post(url='https://memefarm-api.memecoin.org/user/verify/link-wallet',
                                      json={
                                          'address': address,
                                          'delegate': address,
                                          'message': message,
                                          'signature': sign
                                      })

            if r.json()['status'] == 'verification_failed':
                logger.info(f'{self.account_token} | Link Wallet Verification Failed, пробую еще раз')
                sleep(15)
                continue

            elif r.json()['status'] == 401 and r.json().get('error') and r.json()['error'] == 'unauthorized':
                logger.error(f'{self.account_token} | Unauthorized')
                raise Unauthorized()

            return r.json()['status'] == 'success', r.text, r.status_code

    def link_wallet(self,
                    account: eth_account.signers.local.LocalAccount,
                    twitter_username: str) -> tuple[bool, str, int]:
        message_to_sign: str = f'This wallet willl be dropped $MEME from your harvested MEMEPOINTS. ' \
                               'If you referred friends, family, lovers or strangers, ' \
                               'ensure this wallet has the NFT you referred.\n\n' \
                               'But also...\n\n' \
                               'Never gonna give you up\n' \
                               'Never gonna let you down\n' \
                               'Never gonna run around and desert you\n' \
                               'Never gonna make you cry\n' \
                               'Never gonna say goodbye\n' \
                               'Never gonna tell a lie and hurt you\n\n' \
                               f'Wallet: {account.address[:5]}...{account.address[-4:]}\n' \
                               f'X account: @{twitter_username}'

        sign = w3.eth.account.sign_message(encode_defunct(text=message_to_sign),
                                           private_key=account.key).signature.hex()

        return self.link_wallet_request(address=account.address,
                                        sign=sign,
                                        message=message_to_sign)

    async def change_twitter_name(self,
                                  twitter_account_name: str) -> tuple[bool, str, int]:
        r = await self.twitter_client.request(url='https://api.twitter.com/1.1/account/update_profile.json',
                                              method='post',
                                              data={
                                                  'name': f'{twitter_account_name} ❤️ Memecoin'
                                              })

        if 'This account is suspended' in await r[0].text():
            raise AccountSuspended(self.account_token)

        if r[0].status == 200:
            return True, await r[0].text(), r[0].status

        return False, await r[0].text(), r[0].status

    async def twitter_name(self,
                           twitter_account_name: str) -> tuple[bool, str, int]:
        if '❤️ Memecoin' not in twitter_account_name:
            change_twitter_name_result, response_text, response_status = await self.change_twitter_name(
                twitter_account_name=twitter_account_name)

            if not change_twitter_name_result:
                logger.error(f'{self.account_token} | Не удалось изменить имя пользователя')
                return False, response_text, response_status

        while True:
            r = self.meme_client.post(url='https://memefarm-api.memecoin.org/user/verify/twitter-name',
                                      headers={
                                          **self.meme_client.headers,
                                          'content-type': None
                                      })

            if r.json()['status'] == 'verification_failed':
                logger.info(f'{self.account_token} | Change Twitter Name Verification Failed, пробую еще раз')
                sleep(15)
                continue

            elif r.json()['status'] == 401 and r.json().get('error') and r.json()['error'] == 'unauthorized':
                raise Unauthorized()

            return r.json()['status'] == 'success', r.text, r.status_code

    async def create_tweet(self,
                           share_message: str) -> tuple[bool, str]:
        r = await self.twitter_client.tweet(
            text=share_message)

        return True, str(r)

    async def share_message(self,
                            share_message: str,
                            verify_url: str,
                            task_name: str) -> tuple[bool, str, int]:
        # try:
        #         create_tweet_status, tweet_id = await self.create_tweet(share_message=share_message)
        #
        # except better_automation.twitter.errors.HTTPException as error:
        #     if 187 in error.api_codes:
        #         pass
        #
        #     else:
        #         raise better_automation.twitter.errors.HTTPException(error.response)
        #
        # else:
        #     if not create_tweet_status:
        #         return False, tweet_id, 0

        while True:
            r = self.meme_client.post(url=verify_url,
                                      headers={
                                          **self.meme_client.headers,
                                          'content-type': None
                                      })

            if r.json()['status'] == 'verification_failed':
                logger.info(f'{self.account_token} | {task_name.title()} Tweet Verification Failed, пробую еще раз')
                sleep(15)
                continue

            elif r.json()['status'] == 401 and r.json().get('error') and r.json()['error'] == 'unauthorized':
                raise Unauthorized()

            return r.json()['status'] == 'success', r.text, r.status_code

    def invite_code(self) -> tuple[bool, str]:
        while True:
            r = self.meme_client.post(url='https://memefarm-api.memecoin.org/user/verify/invite-code',
                                      json={
                                          'code': config.REF_CODE
                                      })

            if r.json()['status'] == 'verification_failed':
                logger.info(f'{self.account_token} | Referral Verification Failed, пробую еще раз')
                sleep(15)
                continue

            elif r.json()['status'] == 401 and r.json().get('error') and r.json()['error'] == 'unauthorized':
                raise Unauthorized()

            return r.json()['status'] == 'success', r.text

    async def follow_quest(self,
                           username: str,
                           follow_id: str):
        # await self.twitter_client.follow(user_id=await self.twitter_client.request_user_id(username=username)) # dont need it

        r = self.meme_client.post(url='https://memefarm-api.memecoin.org/user/verify/twitter-follow',
                                  json={
                                      'followId': follow_id
                                  })

        return r.json()['status'] == 'success', r.text

    async def get_oauth_auth_tokens(self) -> tuple[str | None, str | None, str | None, str, int]:
        while True:
            headers: dict = self.twitter_client._headers

            if headers.get('content-type'):
                del headers['content-type']

            headers[
                'accept'] = ('text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,'
                             '*/*;q=0.8,application/signed-exchange;v=b3;q=0.7')

            if not self.twitter_client.ct0:
                self.twitter_client.set_ct0(await self.twitter_client._request_ct0())

            while True:
                try:
                    r = await self.twitter_client.request(url='https://memefarm-api.memecoin.org/user/twitter-auth',
                                                          method='get',
                                                          params={
                                                              'callback': 'https://www.memecoin.org/farming'
                                                          },
                                                          headers=headers)

                except better_automation.twitter.errors.BadRequest as error:
                    logger.warning(f'{self.account_token} | BadRequest: {error}, пробую еще раз')

                else:
                    break

            if BeautifulSoup(await r[0].text(), 'lxml').find('iframe', {
                'id': 'arkose_iframe'
            }):
                logger.info(f'{self.account_token} | Обнаружена капча на аккаунте, пробую решить')

                SolveCaptcha(auth_token=self.twitter_client.auth_token,
                             ct0=self.twitter_client.ct0).solve_captcha(
                    proxy=Proxy.from_str(proxy=self.account_proxy).as_url if self.account_proxy else None)
                continue

            if 'https://www.memecoin.org/farming?oauth_token=' in (await r[0].text()):
                return 'https://www.memecoin.org/farming?oauth_token=' + \
                       (await r[0].text()).split('https://www.memecoin.org/farming?oauth_token=')[-1].split('"')[
                           0].replace('&amp;', '&'), None, None, await r[0].text(), r[0].status

            auth_token_html = BeautifulSoup(await r[0].text(), 'lxml').find('input', {
                'name': 'authenticity_token'
            })
            oauth_token_html = BeautifulSoup(await r[0].text(), 'lxml').find('input', {
                'name': 'oauth_token'
            })

            if not auth_token_html or not oauth_token_html:
                logger.warning(f'{self.account_token} | Не удалось обнаружить Auth/OAuth Token на странице, '
                             f'пробую еще раз, статус: {r[0].status}')
                continue

            auth_token: str = auth_token_html.get('value', '')
            oauth_token: str = oauth_token_html.get('value', '')

            return None, auth_token, oauth_token, await r[0].text(), r[0].status

    async def make_auth(self,
                        oauth_token: str,
                        auth_token: str) -> tuple[str | bool, str]:
        while True:
            if not self.twitter_client.ct0:
                self.twitter_client.set_ct0(await self.twitter_client._request_ct0())

            r = await self.twitter_client.request(url='https://api.twitter.com/oauth/authorize',
                                                  method='post',
                                                  data={
                                                      'authenticity_token': auth_token,
                                                      'redirect_after_login': f'https://api.twitter.com/oauth'
                                                                              f'/authorize?oauth_token={oauth_token}',
                                                      'oauth_token': oauth_token
                                                  },
                                                  headers={
                                                      **self.twitter_client._headers,
                                                      'content-type': 'application/x-www-form-urlencoded'
                                                  })

            if 'This account is suspended' in await r[0].text():
                raise AccountSuspended(self.account_token)

            if 'https://www.memecoin.org/farming?oauth_token=' in await r[0].text():
                location: str = 'https://www.memecoin.org/farming?oauth_token=' + \
                                (await r[0].text()).split('https://www.memecoin.org/farming?oauth_token=')[-1].split(
                                    '"')[0].replace('&amp;', '&')

                return location, await r[0].text()

            return False, await r[0].text()

    async def start_reger(self) -> bool:
        for _ in range(config.REPEATS_ATTEMPTS):
            try:
                async with aiohttp.ClientSession(
                        connector=await get_connector(
                            proxy=self.account_proxy) if self.account_proxy else await get_connector(
                            proxy=None)) as aiohttp_twitter_session:
                    self.twitter_client: better_automation.twitter.api.TwitterAPI = TwitterAPI(
                        session=aiohttp_twitter_session,
                        auth_token=self.account_token)

                    if not self.twitter_client.ct0:
                        self.twitter_client.set_ct0(await self.twitter_client._request_ct0())

                    location, auth_token, oauth_token, response_text, response_status = await self.get_oauth_auth_tokens()

                    if not location:
                        if not check_empty_value(value=auth_token,
                                                 account_token=self.account_token) \
                                or not check_empty_value(value=oauth_token,
                                                         account_token=self.account_token):
                            logger.error(
                                f'{self.account_token} | Ошибка при получении OAuth / Auth Token, '
                                f'статус: {response_text}')

                            return False

                        location, response_text = await self.make_auth(oauth_token=oauth_token,
                                                                       auth_token=auth_token)

                        if not check_empty_value(value=location,
                                                 account_token=self.account_token):
                            logger.error(
                                f'{self.account_token} | Ошибка при авторизации через Twitter, '
                                f'статус: {response_status}')
                            return False

                    if parse_qs(urlparse(location).query).get('redirect_after_login') \
                            or not parse_qs(urlparse(location).query).get('oauth_token') \
                            or not parse_qs(urlparse(location).query).get('oauth_verifier'):
                        logger.warning(
                            f'{self.account_token} | Не удалось обнаружить OAuth Token / OAuth Verifier в '
                            f'ссылке: {location}')
                        continue

                    oauth_token: str = parse_qs(urlparse(location).query)['oauth_token'][0]
                    oauth_verifier: str = parse_qs(urlparse(location).query)['oauth_verifier'][0]
                    access_token: str = ''

                    while self.account_too_new_attempts < config.ACCOUNT_TOO_NEW_ATTEMPTS:
                        self.meme_client = tls_client.Session(client_identifier=choice([
                            'Chrome110',
                            'chrome111',
                            'chrome112'
                        ]))
                        self.meme_client.headers.update({
                            'user-agent': choice([
                                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                                'Chrome/112.0.0.0 Safari/537.36',
                                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                                'Chrome/116.0.5845.962 YaBrowser/23.9.1.962 Yowser/2.5 Safari/537.36'
                            ]),
                            'accept': 'application/json',
                            'accept-language': 'ru,en;q=0.9,vi;q=0.8,es;q=0.7,cy;q=0.6',
                            'content-type': 'application/json',
                            'origin': 'https://www.memecoin.org',
                            'referer': 'https://www.memecoin.org/'
                        })

                        if self.account_proxy:
                            self.meme_client.proxies.update({
                                'http': self.account_proxy,
                                'https': self.account_proxy
                            })

                        r = self.meme_client.post(url='https://memefarm-api.memecoin.org/user/twitter-auth1',
                                                  json={
                                                      'oauth_token': oauth_token,
                                                      'oauth_verifier': oauth_verifier
                                                  })

                        if r.json().get('error', '') == 'account_too_new':
                            self.account_too_new_attempts += 1
                            if self.account_too_new_attempts != config.ACCOUNT_TOO_NEW_ATTEMPTS:
                                logger.warning(f'{self.account_token} | Account Too New')
                            continue

                        if r.json().get('error', '') == 'Unauthorized':
                            raise Unauthorized()

                        access_token: str = r.json().get('accessToken', '')

                        if not access_token:
                            logger.warning(
                                f'{self.account_token} | Не удалось обнаружить Access Token в ответе, пробую еще раз, '
                                f'статус: {r.status_code}')
                            continue

                        break

                    else:
                        logger.error(f'{self.account_token} | Account Too New') # out of attemepts

                        async with aiofiles.open('account_too_new.txt', 'a', encoding='utf-8-sig') as f:
                            await f.write(f'{self.account_token}\n')

                        return False

                    if self.user_action == 3:
                        tasks_dict = self.get_tasks()
                        for task in tasks_dict['tasks']:
                            if task['id'] == 'linkWallet':
                                if task['completed']:
                                    adv_text = ':WALLET_ALREADY_CONNECTED'
                                    logger.warning(f'{self.account_token} | Token Valid But Wallet Already Connected!!!')
                                else:
                                    logger.success(f'{self.account_token} | Token Valid')
                                    adv_text = ''
                        async with aiofiles.open('result/stat_working_twitters.txt', mode='a+', encoding='utf-8-sig') as f:
                            await f.write(f'{self.account_token}{adv_text}\n')
                        return True

                    self.meme_client.headers.update({
                        'authorization': f'Bearer {access_token}'
                    })

                    if not self.account_private_key:
                        account: eth_account.signers.local.LocalAccount = generate_eth_account()

                    else:
                        account: eth_account.signers.local.LocalAccount = get_account(
                            private_key=self.account_private_key)

                    tasks_dict: dict = self.get_tasks()
                    twitter_username, twitter_account_name = self.get_twitter_account_names()
                    all_tasks: list = tasks_dict['tasks'] + tasks_dict['timely']

                    if len(all_tasks) - sum([current_task['completed'] for current_task in all_tasks]) != 0:

                        for current_task in tasks_dict['tasks'] + tasks_dict['timely']:
                            if current_task['completed']:
                                continue

                            match current_task['id']:
                                case 'connect':
                                    continue

                                case 'linkWallet':
                                    link_wallet_result, response_text, response_status = self.link_wallet(account=account,
                                                                                                          twitter_username=twitter_username)

                                    if link_wallet_result:
                                        logger.success(f'{self.account_token} | Успешно привязал кошелек')

                                        async with aiofiles.open(file='registered.txt', mode='a',
                                                                 encoding='utf-8-sig') as f:
                                            await f.write(
                                                f'{self.account_token};{self.account_proxy if self.account_proxy else ""};'
                                                f'{account.key.hex()}\n')

                                        if config.SLEEP_BETWEEN_TASKS and current_task != \
                                                (tasks_dict['tasks'] + tasks_dict['timely'])[-1]:
                                            time_to_sleep: int = format_range(value=config.SLEEP_BETWEEN_TASKS,
                                                                              return_randint=True)
                                            logger.info(
                                                f'{self.account_token} | Сплю {time_to_sleep} сек. перед '
                                                f'выполнением следующего таска')
                                            await asyncio.sleep(delay=time_to_sleep)

                                    else:
                                        logger.error(
                                            f'{self.account_token} | Не удалось привязать кошелек, статус: {response_status}')

                                case 'twitterName':
                                    twitter_username_result, response_text, response_status = await self.twitter_name(
                                        twitter_account_name=twitter_account_name)

                                    if twitter_username_result:
                                        logger.success(
                                            f'{self.account_token} | Успешно получил бонус за MEMELAND в никнейме')

                                        if config.SLEEP_BETWEEN_TASKS and current_task != \
                                                (tasks_dict['tasks'] + tasks_dict['timely'])[-1]:
                                            time_to_sleep: int = format_range(value=config.SLEEP_BETWEEN_TASKS,
                                                                              return_randint=True)
                                            logger.info(
                                                f'{self.account_token} | Сплю {time_to_sleep} сек. перед '
                                                f'выполнением следующего таска')
                                            await asyncio.sleep(delay=time_to_sleep)

                                    else:
                                        logger.error(f'{self.account_token} | Не удалось получить бонус за MEMELAND в '
                                                     f'никнейме, статус: {response_status}')

                                case 'shareMessage':
                                    share_message_result, response_text, response_status = await self.share_message(
                                        share_message=f'Hi, my name is @{twitter_username}, and I’m a $MEME (@Memecoin) '
                                                      f'farmer'
                                                      'at @Memeland.\n\nOn my honor, I promise that I will do my best '
                                                      'to do my duty to my own bag, and to farm #MEMEPOINTS at '
                                                      'all times.\n\nIt ain’t much, but it’s honest work. 🧑‍🌾 ',
                                        verify_url='https://memefarm-api.memecoin.org/user/verify/share-message',
                                    task_name='Meme')

                                    if share_message_result:
                                        logger.success(f'{self.account_token} | Успешно получил бонус за твит Meme')

                                        if config.SLEEP_BETWEEN_TASKS and current_task != \
                                                (tasks_dict['tasks'] + tasks_dict['timely'])[-1]:
                                            time_to_sleep: int = format_range(value=config.SLEEP_BETWEEN_TASKS,
                                                                              return_randint=True)
                                            logger.info(
                                                f'{self.account_token} | Сплю {time_to_sleep} сек. перед '
                                                f'выполнением следующего таска')
                                            await asyncio.sleep(delay=time_to_sleep)

                                    else:
                                        logger.error(
                                            f'{self.account_token} | Не удалось создать твит, статус: {response_status}')

                                case 'inviteCode':
                                    invite_code_result, response_text = self.invite_code()

                                    if invite_code_result:
                                        logger.success(f'{self.account_token} | Успешно ввел реф.код')

                                        if config.SLEEP_BETWEEN_TASKS and current_task != \
                                                (tasks_dict['tasks'] + tasks_dict['timely'])[-1]:
                                            time_to_sleep: int = format_range(value=config.SLEEP_BETWEEN_TASKS,
                                                                              return_randint=True)
                                            logger.info(
                                                f'{self.account_token} | Сплю {time_to_sleep} сек. перед '
                                                f'выполнением следующего таска')
                                            await asyncio.sleep(delay=time_to_sleep)

                                    else:
                                        logger.error(
                                            f'{self.account_token} | Не удалось ввести реф.код, статус: {r.status_code}')

                                case 'followMemeland' | 'followMemecoin' | 'follow9gagceo' | 'followGMShowofficial' | 'follow0xChar':
                                    follow_result, response_text = await self.follow_quest(
                                        username=current_task['id'].replace('follow', ''),
                                        follow_id=current_task['id'])

                                    if follow_result:
                                        logger.success(
                                            f'{self.account_token} | Успешно подписался на '
                                            f'{current_task["id"].replace("follow", "")}')

                                        if config.SLEEP_BETWEEN_TASKS and current_task != \
                                                (tasks_dict['tasks'] + tasks_dict['timely'])[-1]:
                                            time_to_sleep: int = format_range(value=config.SLEEP_BETWEEN_TASKS,
                                                                              return_randint=True)
                                            logger.info(
                                                f'{self.account_token} | Сплю {time_to_sleep} сек. перед '
                                                f'выполнением следующего таска')
                                            await asyncio.sleep(delay=time_to_sleep)

                                    else:
                                        logger.error(
                                            f'{self.account_token} | Не удалось подписаться на '
                                            f'{current_task["id"].replace("follow", "")}: {response_text}')

                                case 'goingToBinance':
                                    share_message_result, response_text, response_status = await self.share_message(
                                        share_message='AHOY! $MEME (@MEMECOIN) IS GOING TO @BINANCE! 🙌\n\nThis is not a '
                                                      'drill! This is not fake news! This is happening!\n\n$MEME is the '
                                                      '39th (not 69th) project on Binance Launchpool! You only have 7 days!'
                                                      ' Come join the farming with your fellow Binancians!\n\n👇 '
                                                      'https://www.binance.com/en/support/announcement/'
                                                      '90ccca2c5d6946ef9439dae41a517578',
                                        verify_url='https://memefarm-api.memecoin.org/user/verify/daily-task/goingToBinance', task_name='Binance')

                                    if share_message_result:
                                        logger.success(
                                            f'{self.account_token} | Успешно получил бонус за твит Binance')

                                        if config.SLEEP_BETWEEN_TASKS and current_task != \
                                                (tasks_dict['tasks'] + tasks_dict['timely'])[-1]:
                                            time_to_sleep: int = format_range(value=config.SLEEP_BETWEEN_TASKS,
                                                                              return_randint=True)
                                            logger.info(
                                                f'{self.account_token} | Сплю {time_to_sleep} сек. перед '
                                                f'выполнением следующего таска')
                                            await asyncio.sleep(delay=time_to_sleep)

                                    else:
                                        logger.error(
                                            f'{self.account_token} | Не удалось создать твит, статус: {response_status}')

                                case 'whatBearMarket':
                                    share_message_result, response_text, response_status = await self.share_message(
                                        share_message='AHOY! $MEME (@MEMECOIN) IS GOING TO @BINANCE! 🙌\n\nThis is not a '
                                                      'drill! This is not fake news! This is happening!\n\n$MEME is the '
                                                      '39th (not 69th) project on Binance Launchpool! You only have 7 days!'
                                                      ' Come join the farming with your fellow Binancians!\n\n👇 '
                                                      'https://www.binance.com/en/support/announcement/'
                                                      '90ccca2c5d6946ef9439dae41a517578',
                                        verify_url='https://memefarm-api.memecoin.org/user/verify/daily-task/whatBearMarket', task_name='BearMarket')

                                    if share_message_result:
                                        logger.success(
                                            f'{self.account_token} | Успешно получил бонус за твит BearMarket')

                                        if config.SLEEP_BETWEEN_TASKS and current_task != \
                                                (tasks_dict['tasks'] + tasks_dict['timely'])[-1]:
                                            time_to_sleep: int = format_range(value=config.SLEEP_BETWEEN_TASKS,
                                                                              return_randint=True)
                                            logger.info(
                                                f'{self.account_token} | Сплю {time_to_sleep} сек. перед '
                                                f'выполнением следующего таска')
                                            await asyncio.sleep(delay=time_to_sleep)

                                    else:
                                        logger.error(
                                            f'{self.account_token} | Не удалось создать твит, статус: {response_status}')

                    await self.all_tasks_done()
                    return True

            except better_automation.twitter.errors.Forbidden as error:
                if 'This account is suspended.' in await error.response.text():
                    async with aiofiles.open('suspended_accounts.txt', 'a', encoding='utf-8-sig') as f:
                        await f.write(f'{self.account_token}\n')

                    logger.error(f'{self.account_token} | Account Suspended')
                    return False

                logger.error(f'{self.account_token} | Forbidden Twitter, статус: {error.response.status}')

            except (Unauthorized, better_automation.twitter.errors.Unauthorized,
                    better_automation.twitter.errors.HTTPException):
                logger.error(f'{self.account_token} | Unauthorized')
                self.account_unauthorized += 1
                if self.account_unauthorized >= config.ACCOUNT_UNAUTHORIZED_ATTEMPTS:
                    return False

            except AccountSuspended as error:
                async with aiofiles.open('suspended_accounts.txt', 'a', encoding='utf-8-sig') as f:
                    await f.write(f'{error}\n')

                logger.error(f'{error} | Account Suspended')
                return False

            except Exception as error:
                logger.error(f'{self.account_token} | Неизвестная ошибка, пробую еще раз: {error}')
                continue

            else:
                return True

        else:
            logger.error(f'{self.account_token} | Empty Attempts')

            async with aiofiles.open('empty_attempts.txt', 'a', encoding='utf-8-sig') as f:
                await f.write(f'{self.account_token}\n')

            return False


    async def all_tasks_done(self):
        tasks_dict = self.get_tasks()
        info_dict = self.get_info()

        wallet = info_dict['wallet']
        inviteCode = info_dict['inviteCode']
        points = tasks_dict['points']['current']

        logger.info(f'{self.account_token} | Все задания успешно выполнены | {points} Поинтов')
        async with aiofiles.open(file='result/success_accs.txt', mode='a+', encoding='utf-8-sig') as f:
            await f.write(f'{self.account_token}:{self.account_private_key}:{points}:{inviteCode}:{wallet}\n')



def start_reger_wrapper(source_data: dict) -> bool:
    try:
        if config.CHANGE_PROXY_URL:
            r = requests.get(config.CHANGE_PROXY_URL)
            logger.info(f'{source_data["account_token"]} | Успешно сменил Proxy, статус: {r.status_code}')

            if config.SLEEP_AFTER_PROXY_CHANGING:
                logger.info(
                    f'{source_data["account_token"]} | Сплю {config.SLEEP_AFTER_PROXY_CHANGING} сек. после смены Proxy')
                sleep(config.SLEEP_AFTER_PROXY_CHANGING)

        return asyncio.run(Reger(source_data=source_data).start_reger())

    except Exception as error:
        logger.error(f'{source_data["account_token"]} | Неизвестная ошибка: {error}')
