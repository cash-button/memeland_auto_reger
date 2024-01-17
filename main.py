from multiprocessing.dummy import Pool
from warnings import filterwarnings
from sys import platform
import itertools
import asyncio
import os

import config
from core import start_reger_wrapper
from utils import logger, validate_token, windowname

from core.solve_captcha import create_task, get_task_result


if platform == "windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


if __name__ == '__main__':

    filterwarnings("ignore")
    if not os.path.isdir('result'): os.mkdir('result')

    with open('twitter_tokens.txt', 'r', encoding='utf-8-sig') as file:
        accounts_list: list[str] = [validate_token(input_string=row.strip()) for row in file]

    accounts_list: list = [item for item in accounts_list if item is not None]

    with open('proxies.txt', 'r', encoding='utf-8-sig') as file:
        proxies_list: list[str] = [row.strip() for row in file]

    window_name = windowname.WindowName(accs_amount=len(accounts_list))

    cycled_proxies_list = itertools.cycle(proxies_list) if proxies_list else None

    logger.info(f'Загружено {len(accounts_list)} твиттеров / {len(proxies_list)} прокси')

    threads: int = 1 if config.CHANGE_PROXY_URL else int(input('\tThreads: '))

    input(' > Start')
    print()

    formatted_accounts_list: list = [
        {
            'account_token': current_account,
            'account_proxy': next(cycled_proxies_list) if cycled_proxies_list else None,
            'window_name': window_name
        } for current_account in accounts_list
    ]

    with Pool(processes=threads) as executor:
        tasks_result: list = executor.map(start_reger_wrapper, formatted_accounts_list)

    success_count: int = sum(tasks_result)
    fail_count: int = len(tasks_result) - sum(tasks_result)

    logger.info(f'Статистика работы: {success_count} SUCCESS | {fail_count} FAILED')

    logger.success('Работа успешно завершена')
    input('\nPress Enter To Exit..')
