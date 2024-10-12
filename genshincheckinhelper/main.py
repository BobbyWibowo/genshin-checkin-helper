"""
@Project   : genshinhelper
@Author    : y1ndan
@Blog      : https://www.yindan.me
@GitHub    : https://github.com/y1ndan
"""

from collections.abc import Iterable
from inspect import iscoroutinefunction
from math import ceil
#from pprint import pprint
from random import randint
from time import sleep
from typing import Tuple
import datetime as dt
import os

import schedule

try:
    import genshinhelper as gh
    from config import config
except ImportError:
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    import genshinhelper as gh
    from genshincheckinhelper.config import config
finally:
    from genshinhelper.utils import log, get_cookies, nested_lookup, minutes_to_hours, MESSAGE_TEMPLATE, DAIRY_TEMPLATE, FINANCE_TEMPLATE
from onepush import notify

import asyncio
import genshin # thesadru/genshin.py
from anticaptchaofficial.geetestproxyless import *

import nest_asyncio
nest_asyncio.apply()

if not config.config_exists:
    log.error('./config/config.json does not exist. Create one based on ./config/config.example.json.')
    exit(1)

version = '1.2.0'
banner = f'''
+----------------------------------------------------------------+
|             🌠  HoYoverse Check-In Helper v{version}               |
+----------------------------------------------------------------+
Project      : genshin-checkin-helper
Description  : More than check-in for HoYoverse games.
Authors      : 银弹GCell(y1ndan), Bobby
Library      : thesadru/genshin.py
------------------------------------------------------------------'''

# PKG_Version  : {gh.__version__}
# Blog         : https://www.yindan.me
# Channel      : https://t.me/genshinhelperupdates

def random_sleep(interval: str):
    seconds = randint(*[int(i) for i in interval.split('-')])
    log.info('Sleeping for {seconds}s...'.format(seconds=seconds))
    sleep(seconds)


def time_in_range(interval: str):
    t1, t2 = interval.split('-')
    now_time = dt.datetime.now().time()
    start = dt.datetime.strptime(t1, '%H:%M').time()
    end = dt.datetime.strptime(t2, '%H:%M').time()
    result = start <= now_time or now_time <= end
    if start <= end:
        result = start <= now_time <= end
    return result


def notify_me(title, content):
    notifier = config.ONEPUSH.get('notifier')
    params = config.ONEPUSH.get('params')
    if not notifier or not params:
        log.info('No notification method configured.')
        return
    log.info('Preparing to send notification...')
    return notify(notifier, title=title, content=content, **params)


def assert_timezone(server=None, conf=config.GENSHINPY):
    display_utc_offset = 0
    server_utc_offset = {
        'cn_gf01': 8,
        'cn_qd01': 8,
        'os_usa': -5,
        'os_euro': 1,
        'os_asia': 8,
        'os_cht': 8,
        'usa01': -5,
        'eur01': 1,
        'overseas01': 8
    }

    if type(conf.get('utc_offset')) == int:
        display_utc_offset = conf.get('utc_offset')
    elif type(server) == str and server_utc_offset[server]:
        display_utc_offset = server_utc_offset[server]

    timezone = dt.timezone(dt.timedelta(hours=display_utc_offset))
    utc_offset_str = f'UTC{"+" if display_utc_offset >= 0 else ""}{display_utc_offset}'
    return timezone, utc_offset_str


def get_genshinpy_accounts(accounts, uids):
    got_accounts = []
    for _uid in uids:
        _uid = int(_uid)
        got_uid = False
        # we always loop through all accounts to make the returned accounts
        # match the order of the desired uids in config
        for a in accounts:
            if a.uid == _uid:
                got_accounts.append(a)
                got_uid = True
                break
        if not got_uid:
            log.info(f'Could not find account matching UID {_uid}.')

    if got_accounts:
        return got_accounts
    else:
        log.info(f'Could not find any account matching UIDs {uids}.')
        return False


def seconds_to_time(seconds):
    seconds = int(seconds)
    if seconds < 0:
        raise ValueError('Input number cannot be negative')

    minute, second = divmod(seconds, 60)
    hour, minute = divmod(minute, 60)
    day, hour = divmod(hour, 24)
    return {
        'day': day,
        'hour': hour,
        'minute': minute,
        'second': second
    }


def display_time(time, short=False, min_units=1, max_units=None):
    if type(time) != dict and not isinstance(time, Tuple):
        raise ValueError('Input time must be a dict or Tuple')

    _time = time
    if isinstance(time, Tuple):
        _time = {
            'day': time[0],
            'hour': time[1],
            'minute': time[2],
            'second': time[3]
        }

    units = {
        # short, singular, plural
        'day': ('d', 'day', 'days'),
        'hour': ('h', 'hour', 'hours'),
        'minute': ('min', 'minute', 'minutes'),
        'second': ('s', 'second', 'seconds')
    }
    units_count = len(units)
    # if unset, assume no max limit
    if (max_units == None): max_units = units_count

    results = []
    done = 0
    for i, k in enumerate(units):
        value = _time[k] if type(_time[k]) == int else 0
        # if non-zero, OR last unit(s) to satisfy min unit(s)
        if value or (done < min_units and i >= units_count - min_units):
            # if there's least 1 non-zero higher unit before this, AND
            # this is last unit to satisfy min unit(s), OR last unit before capping max unit(s)
            prepend = 'and ' if results and (i == units_count - 1 or done + 1 >= max_units) else ''
            unit = units[k][0] if short else (units[k][1] if value == 1 else units[k][2])
            results.append('{}{} {}'.format(prepend, value, unit))
            done += 1
            if (done >= max_units): break

    return ' '.join(results)


def task_common(r, d, text_temp1, text_temp2):
    result = []
    for i in range(len(r)):
        if d and d[i]:
            d[i]['month'] = gh.month()
            r[i]['addons'] = text_temp2.format(**d[i])
        message = text_temp1.format(**r[i])
        result.append(message)
    return result


# untested
def taskhoyolab(cookie):
    t = gh.Genshin(cookie)
    r = t.sign()
    d = t.month_dairy
    return task_common(r, d, MESSAGE_TEMPLATE, DAIRY_TEMPLATE)


async def solve_geetest(client: genshin.Client, gt, challenge):
    if not (config.ANTICAPTCHA_API_KEY):
        log.error('"ANTICAPTCHA_API_KEY" config missing, unable to solve Geetest captcha.')
        return 0

    log.info('Solving Geetest captcha...')
    url = str(genshin.client.routes.GAME_RISKY_CHECK_URL.get_url(client.region))

    solver = geetestProxyless()
    solver.set_key(config.ANTICAPTCHA_API_KEY)
    solver.set_website_url(url)
    solver.set_gt_key(gt)
    solver.set_challenge_key(challenge)

    solution = solver.solve_and_return_solution()
    if solution != 0:
        log.info('Geetest captcha solved, continuing...')
        return solution

    log.error(f'[{solver.error_code}] Geetest captcha solver failed.')
    return 0


async def call_safely(client: genshin.Client, func, *args, **kwargs) -> tuple[any, bool]:
    geetest_triggered = False

    try:
        _ = await func(*args, **kwargs)
    except genshin.GeetestError as e:
        log.info('Geetest triggered...')
        geetest_triggered = True

        mmt = await client.create_mmt()

        solution = await solve_geetest(client, mmt.gt, mmt.challenge)
        if solution == 0:
            raise e

        mmt_result = genshin.models.MMTResult(
            geetest_challenge = solution['challenge'],
            geetest_validate = solution['validate'],
            geetest_seccode = solution['seccode']
        )

        await client.verify_mmt(mmt_result)
        _ = await func(*args, **kwargs)
    except genshin.DailyGeetestTriggered as e:
        log.info('Geetest triggered during daily reward claim...')
        geetest_triggered = True

        solution = await solve_geetest(client, e.gt, e.challenge)
        if solution == 0:
            raise e

        _ = await func(*args, **dict(kwargs, challenge=solution))

    return _, geetest_triggered


async def taskgenshinpy(cookie):
    try:
        result = []

        client = genshin.Client(game=genshin.Game.GENSHIN)
        client.set_cookies(cookie)

        log.info('Preparing to get user game roles information...')
        _accounts = list(filter(lambda account: 'hk4e' in account.game_biz, await client.get_game_accounts()))
        if not _accounts:
            return log.info('There are no Genshin accounts associated to this HoYoverse account.')

        CLAIM_TEMPLATE = '''    Today's reward: {name} x {amount}
    Total monthly check-ins: {claimed_rewards} day(s)
    Status: {status}'''

        DIARY_TEMPLATE = '''    {display_name}'s Diary: {month}
    💠 Primogems: {current_primogems}
    🌕 Mora: {current_mora}'''

        accounts = None
        if config.GENSHINPY.get('uids'):
            uids = config.GENSHINPY.get('uids').split('#')
            accounts = get_genshinpy_accounts(_accounts, uids)
            if not accounts:
                return
        else:
            accounts = _accounts

        # use first uid for api calls that are uid-dependant (e.g. get_genshin_diary)
        client.uid = accounts[0].uid

        date_appended = False
        for account in accounts:
            message = ''
            if not date_appended or type(config.GENSHINPY.get('utc_offset')) != int:
                timezone, utc_offset_str = assert_timezone(server=account.server)
                today = f'{dt.datetime.now(timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}' if timezone else 'N/A'
                message += f'📅 {today}\n'
                date_appended = True
            message += f'🔅 {account.nickname} {account.server_name} Lv. {account.level}\n'
            result.append(message)

        data = {}
        geetest_triggered = False

        try:
            log.info('Preparing to claim daily reward...')
            response: tuple[genshin.models.DailyReward, bool] = await call_safely(client, client.claim_daily_reward)
            reward = response[0]
            geetest_triggered = response[1]
        except genshin.AlreadyClaimed:
            log.info('Preparing to get claimed reward information...')
            claimed = await client.claimed_rewards(limit=1)
            data['status'] = '👀 You have already checked-in'
            data['name'] = claimed[0].name
            data['amount'] = claimed[0].amount
        else:
            data['status'] = 'OK\n    Olah! Odomu'
            data['name'] = reward.name
            data['amount'] = reward.amount

        if 'name' in data and 'amount' in data:
            data['today_reward'] = '{name} x {amount}'.format(**data)
        else:
            data['today_reward'] = 'N/A'

        log.info('Preparing to get monthly rewards information...')
        reward_info = await client.get_reward_info()
        data['claimed_rewards'] = reward_info.claimed_rewards
        claim_message = CLAIM_TEMPLATE.format(**data)
        result.append(claim_message)

        if not config.GENSHINPY.get('skip_diary'):
            try:
                log.info(f'Preparing to get traveler\'s diary for UID {accounts[0].uid}...')
                diary = await client.get_genshin_diary()
                diary_data = {
                    'display_name': f'{accounts[0].nickname}' if len(accounts) > 1 else 'Traveler',
                    'month': dt.datetime.strptime(str(diary.month), '%m').strftime('%B'),
                    'current_primogems': diary.data.current_primogems,
                    'current_mora': diary.data.current_mora
                }
                daily_addons = DIARY_TEMPLATE.format(**diary_data)
                result.append(f'\n{daily_addons}')
            except Exception as e:
                log.warning(str(e))
                result.append('\n    Unable to get traveler\'s diary.')

        if geetest_triggered:
            result.append('\n🤖 Geetest captcha triggered for this request.')
    finally:
        log.info('Task finished.')
    return result


async def taskgenshinpyhonkai(cookie):
    try:
        result = []

        client = genshin.Client(game=genshin.Game.HONKAI)
        client.set_cookies(cookie)

        log.info('Preparing to get user game roles information...')
        _accounts = list(filter(lambda account: 'bh3' in account.game_biz, await client.get_game_accounts()))
        if not _accounts:
            return log.info('There are no Honkai accounts associated to this HoYoverse account.')

        CLAIM_TEMPLATE = '''    Today's reward: {name} x {amount}
    Total monthly check-ins: {claimed_rewards} day(s)
    Status: {status}'''

        accounts = None
        if config.GENSHINPY_HONKAI.get('uids'):
            uids = config.GENSHINPY_HONKAI.get('uids').split('#')
            accounts = get_genshinpy_accounts(_accounts, uids)
            if not accounts:
                return
        else:
            accounts = _accounts

        # use first uid for api calls that are uid-dependant
        client.uid = accounts[0].uid

        date_appended = False
        for account in accounts:
            message = ''
            if not date_appended or type(config.GENSHINPY_HONKAI.get('utc_offset')) != int:
                timezone, utc_offset_str = assert_timezone(server=account.server, conf=config.GENSHINPY_HONKAI)
                today = f'{dt.datetime.now(timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}' if timezone else 'N/A'
                message += f'📅 {today}\n'
                date_appended = True
            message += f'🔅 {account.nickname} {account.server_name} Lv. {account.level}\n'
            result.append(message)

        data = {}
        geetest_triggered = False

        try:
            log.info('Preparing to claim daily reward...')
            response: tuple[genshin.models.DailyReward, bool] = await call_safely(client, client.claim_daily_reward)
            reward = response[0]
            geetest_triggered = response[1]
        except genshin.AlreadyClaimed:
            log.info('Preparing to get claimed reward information...')
            claimed = await client.claimed_rewards(limit=1)
            data['status'] = '👀 You have already checked-in'
            data['name'] = claimed[0].name
            data['amount'] = claimed[0].amount
        else:
            data['status'] = 'OK'
            data['name'] = reward.name
            data['amount'] = reward.amount

        log.info('Preparing to get monthly rewards information...')
        reward_info = await client.get_reward_info()
        data['claimed_rewards'] = reward_info.claimed_rewards
        claim_message = CLAIM_TEMPLATE.format(**data)
        result.append(claim_message)

        if geetest_triggered:
            result.append('\n🤖 Geetest captcha triggered for this request.')
    finally:
        log.info('Task finished.')
    return result


async def taskgenshinpystarrail(cookie):
    try:
        result = []

        client = genshin.Client(game=genshin.Game.STARRAIL)
        client.set_cookies(cookie)

        log.info('Preparing to get user game roles information...')
        _accounts = list(filter(lambda account: 'hkrpg' in account.game_biz, await client.get_game_accounts()))
        if not _accounts:
            return log.info('There are no Star Rail accounts associated to this HoYoverse account.')

        CLAIM_TEMPLATE = '''    Today's reward: {name} x {amount}
    Total monthly check-ins: {claimed_rewards} day(s)
    Status: {status}'''

        DIARY_TEMPLATE = '''    {display_name}'s Monthly Calendar: {month}
    💎 Stellar Jade: {current_hcoin}
    🎫 Pass & Special Pass: {current_rails_pass}'''

        accounts = None
        if config.GENSHINPY_STARRAIL.get('uids'):
            uids = config.GENSHINPY_STARRAIL.get('uids').split('#')
            accounts = get_genshinpy_accounts(_accounts, uids)
            if not accounts:
                return
        else:
            accounts = _accounts

        # use first uid for api calls that are uid-dependant
        client.uid = accounts[0].uid

        date_appended = False
        for account in accounts:
            message = ''
            if not date_appended or type(config.GENSHINPY_STARRAIL.get('utc_offset')) != int:
                timezone, utc_offset_str = assert_timezone(server=account.server, conf=config.GENSHINPY_STARRAIL)
                today = f'{dt.datetime.now(timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}' if timezone else 'N/A'
                message += f'📅 {today}\n'
                date_appended = True
            message += f'🔅 {account.nickname} {account.server_name} Lv. {account.level}\n'
            result.append(message)

        data = {}
        geetest_triggered = False

        try:
            log.info('Preparing to claim daily reward...')
            response: tuple[genshin.models.DailyReward, bool] = await call_safely(client, client.claim_daily_reward)
            reward = response[0]
            geetest_triggered = response[1]
        except genshin.AlreadyClaimed:
            log.info('Preparing to get claimed reward information...')
            claimed = await client.claimed_rewards(limit=1)
            data['status'] = '👀 You have already checked-in'
            data['name'] = claimed[0].name
            data['amount'] = claimed[0].amount
        else:
            data['status'] = 'OK'
            data['name'] = reward.name
            data['amount'] = reward.amount

        log.info('Preparing to get monthly rewards information...')
        reward_info = await client.get_reward_info()
        data['claimed_rewards'] = reward_info.claimed_rewards
        claim_message = CLAIM_TEMPLATE.format(**data)

        result.append(claim_message)

        if not config.GENSHINPY_STARRAIL.get('skip_diary'):
            try:
                log.info(f'Preparing to get trailblazer\'s monthly calendar for UID {accounts[0].uid}...')
                diary = await client.get_starrail_diary()
                diary_data = {
                    'display_name': f'{accounts[0].nickname}' if len(accounts) > 1 else 'Trailblazer',
                    'month': f'{dt.datetime.strptime(str(diary.month)[4:], "%m").strftime("%B")} {str(diary.month)[:4]}',
                    'current_hcoin': diary.data.current_hcoin,
                    'current_rails_pass': diary.data.current_rails_pass
                }
                daily_addons = DIARY_TEMPLATE.format(**diary_data)
                result.append(f'\n{daily_addons}')
            except Exception as e:
                log.warning(str(e))
                result.append('\n    Unable to get trailblazer\'s monthly calendar.')

        if geetest_triggered:
            result.append('\n🤖 Geetest captcha triggered for this request.')
    finally:
        log.info('Task finished.')
    return result


async def taskgenshinpyzzz(cookie):
    try:
        result = []

        client = genshin.Client(game=genshin.Game.ZZZ)
        client.set_cookies(cookie)

        log.info('Preparing to get user game roles information...')
        _accounts = list(filter(lambda account: 'nap' in account.game_biz, await client.get_game_accounts()))
        if not _accounts:
            return log.info('There are no Zenless Zone Zero accounts associated to this HoYoverse account.')

        CLAIM_TEMPLATE = '''    Today's reward: {name} x {amount}
    Total monthly check-ins: {claimed_rewards} day(s)
    Status: {status}'''

        accounts = None
        if config.GENSHINPY_ZZZ.get('uids'):
            uids = config.GENSHINPY_ZZZ.get('uids').split('#')
            accounts = get_genshinpy_accounts(_accounts, uids)
            if not accounts:
                return
        else:
            accounts = _accounts

        # use first uid for api calls that are uid-dependant
        client.uid = accounts[0].uid

        date_appended = False
        for account in accounts:
            message = ''
            if not date_appended or type(config.GENSHINPY_ZZZ.get('utc_offset')) != int:
                timezone, utc_offset_str = assert_timezone(server=account.server, conf=config.GENSHINPY_ZZZ)
                today = f'{dt.datetime.now(timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}' if timezone else 'N/A'
                message += f'📅 {today}\n'
                date_appended = True
            message += f'🔅 {account.nickname} {account.server_name} Lv. {account.level}\n'
            result.append(message)

        data = {}
        geetest_triggered = False

        try:
            log.info('Preparing to claim daily reward...')
            response: tuple[genshin.models.DailyReward, bool] = await call_safely(client, client.claim_daily_reward)
            reward = response[0]
            geetest_triggered = response[1]
        except genshin.AlreadyClaimed:
            log.info('Preparing to get claimed reward information...')
            claimed = await client.claimed_rewards(limit=1)
            data['status'] = '👀 You have already checked-in'
            data['name'] = claimed[0].name
            data['amount'] = claimed[0].amount
        else:
            data['status'] = 'OK'
            data['name'] = reward.name
            data['amount'] = reward.amount

        log.info('Preparing to get monthly rewards information...')
        reward_info = await client.get_reward_info()
        data['claimed_rewards'] = reward_info.claimed_rewards
        claim_message = CLAIM_TEMPLATE.format(**data)
        result.append(claim_message)

        if geetest_triggered:
            result.append('\n🤖 Geetest captcha triggered for this request.')
    finally:
        log.info('Task finished.')
    return result


task_list = [{
    'name': 'HoYoLAB Community',
    'cookies': get_cookies(config.COOKIE_HOYOLAB),
    'function': taskhoyolab
}, {
    'name': 'Genshin Impact',
    'cookies': get_cookies(config.GENSHINPY.get('cookies')),
    'function': taskgenshinpy
}, {
    'name': 'Honkai Impact 3',
    'cookies': get_cookies(config.GENSHINPY_HONKAI.get('cookies')),
    'function': taskgenshinpyhonkai
}, {
    'name': 'Honkai: Star Rail',
    'cookies': get_cookies(config.GENSHINPY_STARRAIL.get('cookies')),
    'function': taskgenshinpystarrail
}, {
    'name': 'Zenless Zone Zero',
    'cookies': get_cookies(config.GENSHINPY_ZZZ.get('cookies')),
    'function': taskgenshinpyzzz
}]


async def run_task(name, cookies, func):
    success_count = 0
    failure_count = 0

    combo_token = nested_lookup(cookies, 'x-rpc-combo_token')
    is_cloudgenshin = False if False in [False for i in combo_token if 'xxxxxx' in i] else True
    if not cookies or not is_cloudgenshin:
        # return a iterable object
        return [success_count, failure_count]

    account_count = len(cookies)
    account_str = 'account' if account_count == 1 else 'accounts'
    log.info(
        'You have {account_count} 「{name}」 {account_str} configured.'.format(
            account_count=account_count, name=name, account_str=account_str))

    result_list = []
    for i, cookie in enumerate(cookies, start=1):
        log.info('Preparing to perform task for account {i}...'.format(i=i))
        raw_result = ''
        try:
            if iscoroutinefunction(func):
                raw_result = await func(cookie)
            else:
                raw_result = func(cookie)
            success_count += 1
        except Exception as e:
            raw_result = e
            log.exception('TRACEBACK')
            failure_count += 1
        finally:
            result_str = ''.join(raw_result) if isinstance(raw_result, Iterable) else raw_result
            result_fmt = f'🌈 No.{i}:\n{result_str}\n'
            result_list.append(result_fmt)
            await asyncio.sleep(1)
        continue

    task_name_fmt = f'🏆 {name}'
    #status_fmt = f'☁️ ✅ {success_count} · ❎ {failure_count}'
    message_box = [success_count, failure_count, task_name_fmt, ''.join(result_list)]
    return message_box


async def job1():
    log.info('Starting daily check-in tasks...')
    random_sleep(config.RANDOM_SLEEP_SECS_RANGE)
    finally_result_dict = {
        i['name']: await run_task(i['name'], i['cookies'], i['function'])
        for i in task_list
    }

    total_success_cnt = sum([i[0] for i in finally_result_dict.values()])
    total_failure_cnt = sum([i[1] for i in finally_result_dict.values()])
    message_list = sum([i[2::] for i in finally_result_dict.values()], [])
    tip = '\nWARNING: Please configure environment variables or config.json file first!\n'
    message_box = '\n'.join(message_list) if message_list else tip

    log.info('RESULT:\n' + message_box)
    if message_box != tip:
        title = f'HoYoverse Check-In Helper ✅ {total_success_cnt} · ❎ {total_failure_cnt}'
        is_markdown = config.ONEPUSH.get('params', {}).get('markdown')
        content = f'```\n{message_box}```' if is_markdown else message_box
        notify_me(title, content)

    log.info('Finished daily check-in tasks.')


async def job2genshinpy():
    if (config.GENSHINPY.get('suspend_check_notes_during_dnd')
            and time_in_range(config.NOTES_TIMER_DO_NOT_DISTURB)):
        log.info('job2genshinpy() skipped due to "suspend_check_notes_during_dnd" option.')
        return

    log.info('Starting real-time notes tasks for Genshin Impact...')
    result = []
    for i in get_cookies(config.GENSHINPY.get('cookies')):
        try:
            client = genshin.Client(game=genshin.Game.GENSHIN)
            client.set_cookies(i)

            log.info('Preparing to get user game roles information...')
            _accounts = list(filter(lambda account: 'hk4e' in account.game_biz, await client.get_game_accounts()))
            if not _accounts:
                return log.info('There are no Genshin accounts associated to this HoYoverse account.')

            # TODO: Wait for genshin.py to support character names again
            #expedition_fmt = '└─ {character_name:<19} {expedition_status}'
            expedition_fmt = '└─ {expedition_status}'
            RESIN_TIMER_TEMPLATE = '''🏆 Genshin Impact
☁️ Real-Time Notes
📅 {today}
🔅 {nickname} {server_name} Lv. {level}
    Original Resin: {current_resin} / {max_resin}{until_resin_recovery_fmt}
     └─ {until_resin_recovery_date_fmt}
    Realm Currency: {realm_currency}
    Daily Commissions: {tasks_fmt}
    Encounter Points: {attendances}
    Daily Commission Rewards: {daily_task_status}
    Enemies of Note: {remaining_resin_discounts} / {max_resin_discounts}{resin_discounts_status}
    Parametric Transformer: {transformer}
    Expedition Limit: {completed_expeditions} / {max_expeditions}'''

            ATTENDANCES_TEMPLATE = '''{attendances_fmt}
    Long-Term Encounter Points: {stored_attendance}{stored_attendance_refresh_fmt}'''

            REALM_CURRENCY_TEMPLATE = '''{current_realm_currency} / {max_realm_currency}{until_realm_currency_recovery_fmt}
     └─ {until_realm_currency_recovery_date_fmt}'''

            TRANSFORMER_TEMPLATE = '''{until_transformer_recovery_fmt}
     └─ {until_transformer_recovery_date_fmt}'''

            accounts = None
            if config.GENSHINPY.get('uids'):
                uids = config.GENSHINPY.get('uids').split('#')
                accounts = get_genshinpy_accounts(_accounts, uids)
                if not accounts:
                    return
            else:
                accounts = _accounts

            for account in accounts:
                log.info(f'Preparing to get notes information for UID {account.uid}...')
                client.uid = account.uid
                response: tuple[genshin.models.Notes, bool] = await call_safely(client, client.get_genshin_notes)
                notes = response[0]
                geetest_triggered = response[1]

                timezone, utc_offset_str = assert_timezone(server=account.server)
                data = {
                    'today': f'{dt.datetime.now(tz=timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}' if timezone else '',
                    'nickname': account.nickname,
                    'server_name': account.server_name,
                    'level': account.level,
                    'current_resin': notes.current_resin,
                    'max_resin': notes.max_resin,
                    'until_resin_recovery_fmt': '',
                    'realm_currency': '',
                    'tasks_fmt': '',
                    'attendances': '',
                    'daily_task_status': '',
                    'remaining_resin_discounts': notes.remaining_resin_discounts,
                    'max_resin_discounts': notes.max_resin_discounts,
                    'resin_discounts_status': ' ⏳' if notes.remaining_resin_discounts > 0 else '',
                    'completed_expeditions': 0,
                    'max_expeditions': notes.max_expeditions
                }

                for task_reward in notes.daily_task.task_rewards:
                    if task_reward.status == 'TaskRewardStatusTakenAward':
                        data['tasks_fmt'] += '✅'
                    elif task_reward.status == 'TaskRewardStatusFinished':
                        data['tasks_fmt'] += '☑️'
                    elif task_reward.status == 'TaskRewardStatusUnfinished':
                        data['tasks_fmt'] += '🔲'

                if notes.daily_task.attendance_visible:
                    data['attendances_fmt'] = ' ' # initial extra space to align with daily commissions
                    for attendance_reward in notes.daily_task.attendance_rewards:
                        if attendance_reward.status == 'AttendanceRewardStatusTakenAward':
                            data['attendances_fmt'] += '✅'
                        elif attendance_reward.status == 'AttendanceRewardStatusWaitTaken':
                            data['attendances_fmt'] += '☑️'
                        elif (attendance_reward.status == 'AttendanceRewardStatusForbid'
                                or attendance_reward.status == 'AttendanceRewardStatusUnfinished'):
                            data['attendances_fmt'] += '🔲'

                    data['stored_attendance'] = f'x{notes.daily_task.stored_attendance}'

                    if isinstance(notes.daily_task.stored_attendance_refresh_countdown, dt.timedelta):
                        until_stored_attendance_refresh = ceil(notes.daily_task.stored_attendance_refresh_countdown.total_seconds())
                        data['stored_attendance_refresh_fmt'] = f'({display_time(seconds_to_time(until_stored_attendance_refresh), short=True, max_units=1)})'
                    else:
                        data['stored_attendance_refresh_fmt'] = ''

                    data['attendances'] = ATTENDANCES_TEMPLATE.format(**data)
                else:
                    data['attendances'] = 'N/A'

                if notes.daily_task.claimed_commission_reward:
                    data['daily_task_status'] = 'All Claimed'
                else:
                    data['daily_task_status'] = f'{notes.daily_task.completed_tasks} / {notes.daily_task.max_tasks} ⏳'

                details = []

                earliest_expedition = False
                for expedition in notes.expeditions:
                    expedition_data = {
                        # TODO: Wait for genshin.py to support character names again
                        #'character_name': (expedition.character.name[:18] + '…') if len(expedition.character.name) > 19 else expedition.character.name
                    }
                    if expedition.finished:
                        expedition_data['expedition_status'] = '✨ Completed!'
                        data['completed_expeditions'] += 1
                    else:
                        remaining_time = ceil(expedition.remaining_time.total_seconds())
                        expedition_data['expedition_status'] = f'({display_time(seconds_to_time(remaining_time), short=True, min_units=2, max_units=2)})'
                        if not earliest_expedition or expedition.completion_time < earliest_expedition:
                            earliest_expedition = expedition.completion_time
                    details.append(expedition_fmt.format(**expedition_data))

                if earliest_expedition:
                    if timezone:
                        details.append(f'└─ Earliest at {earliest_expedition.astimezone(tz=timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}')
                    else:
                        details.append(f'└─ Earliest at {earliest_expedition.strftime("%Y-%m-%d %I:%M %p")}')

                is_full = notes.current_resin >= notes.max_resin
                if is_full:
                    data['until_resin_recovery_date_fmt'] = '✨ Full!'
                else:
                    until_resin_recovery = ceil(notes.remaining_resin_recovery_time.total_seconds())
                    data['until_resin_recovery_fmt'] = f' ({display_time(seconds_to_time(until_resin_recovery), short=True, min_units=2, max_units=2)})'
                    if timezone:
                        data['until_resin_recovery_date_fmt'] = f'Full at {notes.resin_recovery_time.astimezone(tz=timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}'
                    else:
                        data['until_resin_recovery_date_fmt'] = f'Full at {notes.resin_recovery_time.strftime("%Y-%m-%d %I:%M %p")}'

                do_realm_currency = bool(notes.max_realm_currency)
                is_realm_currency_full = False
                if do_realm_currency:
                    data['current_realm_currency'] = notes.current_realm_currency
                    data['max_realm_currency'] = notes.max_realm_currency

                    is_realm_currency_full = notes.current_realm_currency >= notes.max_realm_currency
                    if is_realm_currency_full:
                        data['until_realm_currency_recovery_date_fmt'] = '✨ Full!'
                    else:
                        until_realm_currency_recovery = ceil(notes.remaining_realm_currency_recovery_time.total_seconds())
                        data['until_realm_currency_recovery_fmt'] = f' ({display_time(seconds_to_time(until_realm_currency_recovery), short=True, min_units=2, max_units=2)})'
                        if timezone:
                            data['until_realm_currency_recovery_date_fmt'] = f'Full at {notes.realm_currency_recovery_time.astimezone(tz=timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}'
                        else:
                            data['until_realm_currency_recovery_date_fmt'] = f'Full at {notes.realm_currency_recovery_time.strftime("%Y-%m-%d %I:%M %p")}'

                    data['realm_currency'] = REALM_CURRENCY_TEMPLATE.format(**data)
                else:
                    data['realm_currency'] = 'N/A'

                do_transformer = notes.remaining_transformer_recovery_time != None
                is_transformer_ready = until_transformer_recovery = False
                if do_transformer:
                    until_transformer_recovery = ceil(notes.remaining_transformer_recovery_time.total_seconds())
                    if until_transformer_recovery > 0:
                        recovery_date_fmt = '%Y-%m-%d'
                        if notes.remaining_transformer_recovery_time.minutes or notes.remaining_transformer_recovery_time.seconds:
                            recovery_date_fmt += ' %I:%M %p'
                        elif notes.remaining_transformer_recovery_time.hours:
                            recovery_date_fmt += ' %I:00 %p'
                        if timezone:
                            data['until_transformer_recovery_date_fmt'] = f'Ready at {notes.transformer_recovery_time.astimezone(tz=timezone).strftime(recovery_date_fmt)} {utc_offset_str}'
                        else:
                            data['until_transformer_recovery_date_fmt'] = f'Ready at {notes.transformer_recovery_time.strftime(recovery_date_fmt)}'
                        short = until_transformer_recovery < 300 # if less than 5 minutes left
                        data['until_transformer_recovery_fmt'] = display_time(time=notes.remaining_transformer_recovery_time.timedata, short=short, max_units=2)
                        data['transformer'] = TRANSFORMER_TEMPLATE.format(**data)
                    else:
                        is_transformer_ready = True
                        data['transformer'] = '✨ Ready!'
                else:
                    data['transformer'] = 'N/A'

                data['expedition_details'] = '\n     '.join(details)

                message = RESIN_TIMER_TEMPLATE.format(**data)
                if details:
                    message += '\n     '.join([''] + details)

                if geetest_triggered:
                    message += '\n🤖 Geetest captcha triggered for this request.'

                result.append(message)
                log.info(message)

                is_markdown = config.ONEPUSH.get('params', {}).get('markdown')
                content = f'```\n{message}```' if is_markdown else message
                status = 'Push conditions have not been met yet, will re-check later as scheduled.'

                IS_NOTIFY_STR = f'UID_{account.uid}_IS_NOTIFY_STR'
                RESIN_NOTIFY_CNT_STR = f'UID_{account.uid}_RESIN_NOTIFY_CNT'
                RESIN_THRESHOLD_NOTIFY_CNT_STR = f'UID_{account.uid}_RESIN_THRESHOLD_NOTIFY_CNT'
                RESIN_LAST_RECOVERY_TIME = f'UID_{account.uid}_RESIN_LAST_RECOVERY_TIME'
                REALM_CURRENCY_NOTIFY_CNT_STR = f'UID_{account.uid}_REALM_CURRENCY_NOTIFY_CNT'
                REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR = f'UID_{account.uid}_REALM_CURRENCY_THRESHOLD_NOTIFY_CNT'
                REALM_CURRENCY_LAST_RECOVERY_TIME = f'UID_{account.uid}_REALM_CURRENCY_LAST_RECOVERY_TIME'
                TRANSFORMER_NOTIFY_CNT_STR = f'UID_{account.uid}_TRANSFORMER_NOTIFY_CNT'
                TRANSFORMER_WAS_READY_STR = f'UID_{account.uid}_TRANSFORMER_WAS_READY'
                EXPEDITION_NOTIFY_CNT_STR = f'UID_{account.uid}_EXPEDITION_NOTIFY_CNT'

                is_first_run = not bool(os.environ.get(IS_NOTIFY_STR))
                os.environ[IS_NOTIFY_STR] = 'False'
                os.environ[RESIN_NOTIFY_CNT_STR] = os.environ[RESIN_NOTIFY_CNT_STR] if os.environ.get(RESIN_NOTIFY_CNT_STR) else '0'
                os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] = os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] if os.environ.get(RESIN_THRESHOLD_NOTIFY_CNT_STR) else '0'
                os.environ[EXPEDITION_NOTIFY_CNT_STR] = os.environ[EXPEDITION_NOTIFY_CNT_STR] if os.environ.get(EXPEDITION_NOTIFY_CNT_STR) else '0'

                is_threshold = False
                try:
                    # default fallback: ~3 hours before capping (8 minutes per resin, so 23 resins for ~3 hours)
                    resin_threshold = int(config.GENSHINPY.get('resin_threshold') or -23)
                    if resin_threshold < 0:
                        is_threshold = notes.current_resin >= (notes.max_resin + resin_threshold)
                    else:
                        is_threshold = notes.current_resin >= resin_threshold
                except:
                    pass

                is_resin_notify = int(os.environ[RESIN_NOTIFY_CNT_STR]) <= config.FULL_STAMINA_REPEAT_NOTIFY
                is_resin_threshold_notify = int(os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR]) < 1
                is_resin_recovery_time_changed = False
                os.environ[RESIN_LAST_RECOVERY_TIME] = os.environ[RESIN_LAST_RECOVERY_TIME] if os.environ.get(RESIN_LAST_RECOVERY_TIME) else str(notes.resin_recovery_time.timestamp())
                is_resin_recovery_time_changed = abs(float(os.environ[RESIN_LAST_RECOVERY_TIME]) - notes.resin_recovery_time.timestamp()) > 400
                is_any_expedition_completed = data['completed_expeditions'] > 0

                is_realm_currency_threshold = is_realm_currency_notify = is_realm_currency_threshold_notify = is_realm_currency_recovery_time_changed = False
                if do_realm_currency:
                    os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] = os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] if os.environ.get(REALM_CURRENCY_NOTIFY_CNT_STR) else '0'
                    os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] = os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] if os.environ.get(REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR) else '0'
                    try:
                        # default fallback: ~3 hours before capping (30 currency per hour if maxed level, so 90 currency for ~3 hours)
                        realm_currency_threshold = int(config.GENSHINPY.get('realm_currency_threshold') or -90)
                        if realm_currency_threshold < 0:
                            is_realm_currency_threshold = notes.current_realm_currency >= (notes.max_realm_currency + realm_currency_threshold)
                        else:
                            is_realm_currency_threshold = notes.current_realm_currency >= realm_currency_threshold
                    except:
                        pass
                    is_realm_currency_notify = int(os.environ[REALM_CURRENCY_NOTIFY_CNT_STR]) <= config.FULL_EXTRAS_REPEAT_NOTIFY
                    is_realm_currency_threshold_notify = int(os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR]) < 1
                    os.environ[REALM_CURRENCY_LAST_RECOVERY_TIME] = os.environ[REALM_CURRENCY_LAST_RECOVERY_TIME] if os.environ.get(REALM_CURRENCY_LAST_RECOVERY_TIME) else str(notes.realm_currency_recovery_time.timestamp())
                    is_realm_currency_recovery_time_changed = abs(float(os.environ[REALM_CURRENCY_LAST_RECOVERY_TIME]) - notes.realm_currency_recovery_time.timestamp()) > 400

                is_transformer_notify = is_transformer_ready_status_changed = False
                if do_transformer:
                    os.environ[TRANSFORMER_NOTIFY_CNT_STR] = os.environ[TRANSFORMER_NOTIFY_CNT_STR] if os.environ.get(TRANSFORMER_NOTIFY_CNT_STR) else '0'
                    is_transformer_notify = int(os.environ[TRANSFORMER_NOTIFY_CNT_STR]) <= config.FULL_EXTRAS_REPEAT_NOTIFY
                    os.environ[TRANSFORMER_WAS_READY_STR] = os.environ[TRANSFORMER_WAS_READY_STR] if os.environ.get(TRANSFORMER_WAS_READY_STR) else ('True' if is_transformer_ready else 'False')
                    was_transformer_ready = os.environ[TRANSFORMER_WAS_READY_STR] == 'True'
                    is_transformer_ready_status_changed = was_transformer_ready != is_transformer_ready

                if is_full and is_resin_notify:
                    os.environ[RESIN_NOTIFY_CNT_STR] = str(int(os.environ[RESIN_NOTIFY_CNT_STR]) + 1)
                    status = f'Original Resin is full! ({os.environ[RESIN_NOTIFY_CNT_STR]}/{config.FULL_STAMINA_REPEAT_NOTIFY + 1})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_threshold and is_resin_threshold_notify:
                    status = 'Original Resin is almost full!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                    os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] = str(int(os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR]) + 1)
                elif is_resin_recovery_time_changed and not is_full:
                    status = 'Original Resin\'s recovery time has changed!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_realm_currency_full and is_realm_currency_notify:
                    os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] = str(int(os.environ[REALM_CURRENCY_NOTIFY_CNT_STR]) + 1)
                    status = f'Realm Currency is full! ({os.environ[REALM_CURRENCY_NOTIFY_CNT_STR]}/{config.FULL_EXTRAS_REPEAT_NOTIFY + 1})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_realm_currency_threshold and is_realm_currency_threshold_notify:
                    status = 'Realm Currency is almost full!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                    os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] = str(int(os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR]) + 1)
                elif is_realm_currency_recovery_time_changed and not is_realm_currency_full:
                    status = 'Realm Currency\'s recovery time has changed!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_transformer_ready and is_transformer_notify:
                    os.environ[TRANSFORMER_NOTIFY_CNT_STR] = str(int(os.environ[TRANSFORMER_NOTIFY_CNT_STR]) + 1)
                    status = f'Parametric Transformer is ready! ({os.environ[TRANSFORMER_NOTIFY_CNT_STR]}/{config.FULL_EXTRAS_REPEAT_NOTIFY + 1})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_transformer_ready_status_changed and not is_transformer_ready:
                    status = 'Parametric Transformer\'s recovery time has changed!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_any_expedition_completed and int(os.environ[EXPEDITION_NOTIFY_CNT_STR]) <= config.FULL_EXTRAS_REPEAT_NOTIFY:
                    os.environ[EXPEDITION_NOTIFY_CNT_STR] = str(int(os.environ[EXPEDITION_NOTIFY_CNT_STR]) + 1)
                    status = f'Expedition{"s" if data["completed_expeditions"] > 1 else ""} completed! ({os.environ[EXPEDITION_NOTIFY_CNT_STR]}/{config.FULL_EXTRAS_REPEAT_NOTIFY + 1})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_first_run:
                    status = 'Real-Time Notes is being monitored!'
                    os.environ[IS_NOTIFY_STR] = 'True'

                os.environ[RESIN_NOTIFY_CNT_STR] = os.environ[RESIN_NOTIFY_CNT_STR] if is_full else '0'
                os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] = os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] if is_threshold else '0'
                os.environ[RESIN_LAST_RECOVERY_TIME] = str(notes.resin_recovery_time.timestamp())
                os.environ[EXPEDITION_NOTIFY_CNT_STR] = os.environ[EXPEDITION_NOTIFY_CNT_STR] if is_any_expedition_completed else '0'

                if do_realm_currency:
                    os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] = os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] if is_realm_currency_full else '0'
                    os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] = os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] if is_realm_currency_threshold else '0'
                    os.environ[REALM_CURRENCY_LAST_RECOVERY_TIME] = str(notes.realm_currency_recovery_time.timestamp())

                if do_transformer:
                    os.environ[TRANSFORMER_NOTIFY_CNT_STR] = os.environ[TRANSFORMER_NOTIFY_CNT_STR] if is_transformer_ready else '0'
                    os.environ[TRANSFORMER_WAS_READY_STR] = 'True' if is_transformer_ready else 'False'

                title = status
                log.info(title)
                if os.environ[IS_NOTIFY_STR] == 'True':
                    notify_me(title, content)
        except genshin.GenshinException as e:
            log.info(e)
        except Exception as e:
            log.exception('EXCEPTION')
        finally:
            log.info('Task finished.')
    return result


async def job2genshinpystarrail():
    if (config.GENSHINPY_STARRAIL.get('suspend_check_notes_during_dnd')
            and time_in_range(config.NOTES_TIMER_DO_NOT_DISTURB)):
        log.info('job2genshinpystarrail() skipped due to "suspend_check_notes_during_dnd" option.')
        return

    log.info('Starting real-time notes tasks for Honkai: Star Rail...')
    result = []
    for i in get_cookies(config.GENSHINPY_STARRAIL.get('cookies')):
        try:
            client = genshin.Client(game=genshin.Game.STARRAIL)
            client.set_cookies(i)

            log.info('Preparing to get user game roles information...')
            _accounts = list(filter(lambda account: 'hkrpg' in account.game_biz, await client.get_game_accounts()))
            if not _accounts:
                return log.info('There are no Star Rail accounts associated to this HoYoverse account.')

            expedition_fmt = '└─ {expedition_name:<19} {expedition_status}'
            STAMINA_TIMER_TEMPLATE = '''🏆 Honkai: Star Rail
☁️ Real-Time Notes
📅 {today}
🔅 {nickname} {server_name} Lv. {level}
    Trailblaze Power: {current_stamina} / {max_stamina}{until_stamina_recovery_fmt}
     └─ {until_stamina_recovery_date_fmt}
    Reserved Power: {current_reserve_stamina} / 2400
    Daily Training: {current_train_score} / {max_train_score}{train_status}
    Simulated Universe: {current_rogue_score} / {max_rogue_score}{rogue_score_status}
    Echo of War: {remaining_weekly_discounts} / {max_weekly_discounts}{weekly_discounts_status}
    Assignment Execution: {completed_expeditions} / {total_expeditions_num}'''

            accounts = None
            if config.GENSHINPY_STARRAIL.get('uids'):
                uids = config.GENSHINPY_STARRAIL.get('uids').split('#')
                accounts = get_genshinpy_accounts(_accounts, uids)
                if not accounts:
                    return
            else:
                accounts = _accounts

            for account in accounts:
                log.info(f'Preparing to get notes information for UID {account.uid}...')
                client.uid = account.uid
                response: tuple[genshin.models.StarRailNote, bool] = await call_safely(client, client.get_starrail_notes)
                notes = response[0]
                geetest_triggered = response[1]

                timezone, utc_offset_str = assert_timezone(server=account.server)
                data = {
                    'today': f'{dt.datetime.now(tz=timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}' if timezone else '',
                    'nickname': account.nickname,
                    'server_name': account.server_name,
                    'level': account.level,
                    'current_stamina': notes.current_stamina,
                    'max_stamina': notes.max_stamina,
                    'until_stamina_recovery_fmt': '',
                    'current_reserve_stamina': notes.current_reserve_stamina,
                    'current_train_score': notes.current_train_score,
                    'max_train_score': notes.max_train_score,
                    'train_status': ' ⏳' if notes.current_train_score < notes.max_train_score else '',
                    'current_rogue_score': notes.current_rogue_score,
                    'max_rogue_score': notes.max_rogue_score,
                    'rogue_score_status': ' ⏳' if notes.current_rogue_score < notes.max_rogue_score else '',
                    'remaining_weekly_discounts': notes.remaining_weekly_discounts,
                    'max_weekly_discounts': notes.max_weekly_discounts,
                    'weekly_discounts_status': ' ⏳' if notes.remaining_weekly_discounts > 0 else '',
                    'completed_expeditions': 0,
                    'total_expeditions_num': notes.total_expedition_num
                }

                details = []

                earliest_expedition = False
                for expedition in notes.expeditions:
                    expedition_data = {
                        'expedition_name': (expedition.name[:18] + '…') if len(expedition.name) > 19 else expedition.name
                    }
                    if expedition.finished:
                        expedition_data['expedition_status'] = '✨ Completed!'
                        data['completed_expeditions'] += 1
                    else:
                        remaining_time = ceil(expedition.remaining_time.total_seconds())
                        expedition_data['expedition_status'] = f'({display_time(seconds_to_time(remaining_time), short=True, min_units=2, max_units=2)})'
                        if not earliest_expedition or expedition.completion_time < earliest_expedition:
                            earliest_expedition = expedition.completion_time
                    details.append(expedition_fmt.format(**expedition_data))

                if earliest_expedition:
                    if timezone:
                        details.append(f'└─ Earliest at {earliest_expedition.astimezone(tz=timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}')
                    else:
                        details.append(f'└─ Earliest at {earliest_expedition.strftime("%Y-%m-%d %I:%M %p")}')

                is_full = notes.current_stamina >= notes.max_stamina
                if is_full:
                    data['until_stamina_recovery_date_fmt'] = '✨ Full!'
                else:
                    until_stamina_recovery = ceil(notes.stamina_recover_time.total_seconds())
                    data['until_stamina_recovery_fmt'] = f' ({display_time(seconds_to_time(until_stamina_recovery), short=True, min_units=2, max_units=2)})'
                    if timezone:
                        data['until_stamina_recovery_date_fmt'] = f'Full at {notes.stamina_recovery_time.astimezone(tz=timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}'
                    else:
                        data['until_stamina_recovery_date_fmt'] = f'Full at {notes.stamina_recovery_time.strftime("%Y-%m-%d %I:%M %p")}'

                data['expedition_details'] = '\n     '.join(details)

                message = STAMINA_TIMER_TEMPLATE.format(**data)
                if details:
                    message += '\n     '.join([''] + details)

                if geetest_triggered:
                    message += '\n🤖 Geetest captcha triggered for this request.'

                result.append(message)
                log.info(message)

                is_markdown = config.ONEPUSH.get('params', {}).get('markdown')
                content = f'```\n{message}```' if is_markdown else message
                status = 'Push conditions have not been met yet, will re-check later as scheduled.'

                IS_NOTIFY_STR = f'UID_SR_{account.uid}_IS_NOTIFY_STR'
                STAMINA_NOTIFY_CNT_STR = f'UID_SR_{account.uid}_STAMINA_NOTIFY_CNT'
                STAMINA_THRESHOLD_NOTIFY_CNT_STR = f'UID_SR_{account.uid}_STAMINA_THRESHOLD_NOTIFY_CNT'
                STAMINA_LAST_RECOVERY_TIME = f'UID_SR_{account.uid}_STAMINA_LAST_RECOVERY_TIME'
                EXPEDITION_NOTIFY_CNT_STR = f'UID_SR_{account.uid}_EXPEDITION_NOTIFY_CNT'

                is_first_run = not bool(os.environ.get(IS_NOTIFY_STR))
                os.environ[IS_NOTIFY_STR] = 'False'
                os.environ[STAMINA_NOTIFY_CNT_STR] = os.environ[STAMINA_NOTIFY_CNT_STR] if os.environ.get(STAMINA_NOTIFY_CNT_STR) else '0'
                os.environ[STAMINA_THRESHOLD_NOTIFY_CNT_STR] = os.environ[STAMINA_THRESHOLD_NOTIFY_CNT_STR] if os.environ.get(STAMINA_THRESHOLD_NOTIFY_CNT_STR) else '0'
                os.environ[EXPEDITION_NOTIFY_CNT_STR] = os.environ[EXPEDITION_NOTIFY_CNT_STR] if os.environ.get(EXPEDITION_NOTIFY_CNT_STR) else '0'

                is_threshold = False
                try:
                    # default fallback: ~3 hours before capping (6 minutes per power, so 30 power for ~3 hours)
                    stamina_threshold = int(config.GENSHINPY_STARRAIL.get('stamina_threshold') or -30)
                    if stamina_threshold < 0:
                        is_threshold = notes.current_stamina >= (notes.max_stamina + stamina_threshold)
                    else:
                        is_threshold = notes.current_stamina >= stamina_threshold
                except:
                    pass

                is_stamina_notify = int(os.environ[STAMINA_NOTIFY_CNT_STR]) <= config.FULL_STAMINA_REPEAT_NOTIFY
                is_stamina_threshold_notify = int(os.environ[STAMINA_THRESHOLD_NOTIFY_CNT_STR]) < 1
                is_stamina_recovery_time_changed = False
                os.environ[STAMINA_LAST_RECOVERY_TIME] = os.environ[STAMINA_LAST_RECOVERY_TIME] if os.environ.get(STAMINA_LAST_RECOVERY_TIME) else str(notes.stamina_recovery_time.timestamp())
                is_stamina_recovery_time_changed = abs(float(os.environ[STAMINA_LAST_RECOVERY_TIME]) - notes.stamina_recovery_time.timestamp()) > 400
                is_any_expedition_completed = data['completed_expeditions'] > 0

                if is_full and is_stamina_notify:
                    os.environ[STAMINA_NOTIFY_CNT_STR] = str(int(os.environ[STAMINA_NOTIFY_CNT_STR]) + 1)
                    status = f'Trailblaze Power is full! ({os.environ[STAMINA_NOTIFY_CNT_STR]}/{config.FULL_STAMINA_REPEAT_NOTIFY + 1})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_threshold and is_stamina_threshold_notify:
                    status = 'Trailblaze Power is almost full!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                    os.environ[STAMINA_THRESHOLD_NOTIFY_CNT_STR] = str(int(os.environ[STAMINA_THRESHOLD_NOTIFY_CNT_STR]) + 1)
                elif is_stamina_recovery_time_changed and not is_full:
                    status = 'Trailblaze Power\'s recovery time has changed!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_any_expedition_completed and int(os.environ[EXPEDITION_NOTIFY_CNT_STR]) <= config.FULL_EXTRAS_REPEAT_NOTIFY:
                    os.environ[EXPEDITION_NOTIFY_CNT_STR] = str(int(os.environ[EXPEDITION_NOTIFY_CNT_STR]) + 1)
                    status = f'Assignment{"s" if data["completed_expeditions"] > 1 else ""} completed! ({os.environ[EXPEDITION_NOTIFY_CNT_STR]}/{config.FULL_EXTRAS_REPEAT_NOTIFY + 1})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_first_run:
                    status = 'Real-Time Notes is being monitored!'
                    os.environ[IS_NOTIFY_STR] = 'True'

                os.environ[STAMINA_NOTIFY_CNT_STR] = os.environ[STAMINA_NOTIFY_CNT_STR] if is_full else '0'
                os.environ[STAMINA_THRESHOLD_NOTIFY_CNT_STR] = os.environ[STAMINA_THRESHOLD_NOTIFY_CNT_STR] if is_threshold else '0'
                os.environ[STAMINA_LAST_RECOVERY_TIME] = str(notes.stamina_recovery_time.timestamp())
                os.environ[EXPEDITION_NOTIFY_CNT_STR] = os.environ[EXPEDITION_NOTIFY_CNT_STR] if is_any_expedition_completed else '0'

                title = status
                log.info(title)
                if os.environ[IS_NOTIFY_STR] == 'True':
                    notify_me(title, content)
        except genshin.GenshinException as e:
            log.info(e)
        except Exception as e:
            log.exception('EXCEPTION')
        finally:
            log.info('Task finished.')
    return result


async def job2genshinpyzzz():
    if (config.GENSHINPY_ZZZ.get('suspend_check_notes_during_dnd')
            and time_in_range(config.NOTES_TIMER_DO_NOT_DISTURB)):
        log.info('job2genshinpyzzz() skipped due to "suspend_check_notes_during_dnd" option.')
        return

    log.info('Starting real-time notes tasks for Zenless Zone Zero...')
    result = []
    for i in get_cookies(config.GENSHINPY_ZZZ.get('cookies')):
        try:
            client = genshin.Client(game=genshin.Game.ZZZ)
            client.set_cookies(i)

            log.info('Preparing to get user game roles information...')
            _accounts = list(filter(lambda account: 'nap' in account.game_biz, await client.get_game_accounts()))
            if not _accounts:
                return log.info('There are no Zenless Zone Zero accounts associated to this HoYoverse account.')

            VIDEO_STORE_STATUS = {
                'REVENUE_AVAILABLE': 'Revenue Available ⏳',
                'WAITING_TO_OPEN': 'Waiting To Open ⏳',
                'CURRENTLY_OPEN': 'Currently Open'
            }

            BATTERY_TIMER_TEMPLATE = '''🏆 Zenless Zone Zero
☁️ Real-Time Notes
📅 {today}
🔅 {nickname} {server_name} Lv. {level}
    Battery Charge: {current_battery} / {max_battery}{until_battery_recovery_fmt}
     └─ {until_battery_recovery_date_fmt}
    Engagement Today: {current_engagement} / {max_engagement}{engagement_status}
    Scratch Card Mania: {scratch_card_status}
    Video Store Management: {video_store_status}'''

            accounts = None
            if config.GENSHINPY_ZZZ.get('uids'):
                uids = config.GENSHINPY_ZZZ.get('uids').split('#')
                accounts = get_genshinpy_accounts(_accounts, uids)
                if not accounts:
                    return
            else:
                accounts = _accounts

            for account in accounts:
                log.info(f'Preparing to get notes information for UID {account.uid}...')
                client.uid = account.uid
                response: tuple[genshin.models.ZZZNotes, bool] = await call_safely(client, client.get_zzz_notes)
                notes = response[0]
                geetest_triggered = response[1]

                timezone, utc_offset_str = assert_timezone(server=account.server)
                data = {
                    'today': f'{dt.datetime.now(tz=timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}' if timezone else '',
                    'nickname': account.nickname,
                    'server_name': account.server_name,
                    'level': account.level,
                    'current_battery': notes.battery_charge.current,
                    'max_battery': notes.battery_charge.max,
                    'until_battery_recovery_fmt': '',
                    'current_engagement': notes.engagement.current,
                    'max_engagement': notes.engagement.max,
                    'engagement_status': ' ⏳' if notes.engagement.current < notes.engagement.max else '',
                    'scratch_card_status': 'Complete' if notes.scratch_card_completed else 'Available ⏳',
                    'video_store_status': VIDEO_STORE_STATUS[notes.video_store_state.name]
                }

                details = []

                is_full = notes.battery_charge.current >= notes.battery_charge.max
                if is_full:
                    data['until_battery_recovery_date_fmt'] = '✨ Full!'
                else:
                    until_battery_recovery = notes.battery_charge.seconds_till_full
                    data['until_battery_recovery_fmt'] = f' ({display_time(seconds_to_time(until_battery_recovery), short=True, min_units=2, max_units=2)})'
                    if timezone:
                        data['until_battery_recovery_date_fmt'] = f'Full at {notes.battery_charge.full_datetime.astimezone(tz=timezone).strftime("%Y-%m-%d %I:%M %p")} {utc_offset_str}'
                    else:
                        data['until_battery_recovery_date_fmt'] = f'Full at {notes.battery_charge.full_datetime.strftime("%Y-%m-%d %I:%M %p")}'

                message = BATTERY_TIMER_TEMPLATE.format(**data)
                if details:
                    message += '\n     '.join([''] + details)

                if geetest_triggered:
                    message += '\n🤖 Geetest captcha triggered for this request.'

                result.append(message)
                log.info(message)

                is_markdown = config.ONEPUSH.get('params', {}).get('markdown')
                content = f'```\n{message}```' if is_markdown else message
                status = 'Push conditions have not been met yet, will re-check later as scheduled.'

                IS_NOTIFY_STR = f'UID_ZZZ_{account.uid}_IS_NOTIFY_STR'
                BATTERY_NOTIFY_CNT_STR = f'UID_ZZZ_{account.uid}_BATTERY_NOTIFY_CNT'
                BATTERY_THRESHOLD_NOTIFY_CNT_STR = f'UID_ZZZ_{account.uid}_BATTERY_THRESHOLD_NOTIFY_CNT'
                BATTERY_LAST_RECOVERY_TIME = f'UID_SR_{account.uid}_BATTERY_LAST_RECOVERY_TIME'

                is_first_run = not bool(os.environ.get(IS_NOTIFY_STR))
                os.environ[IS_NOTIFY_STR] = 'False'
                os.environ[BATTERY_NOTIFY_CNT_STR] = os.environ[BATTERY_NOTIFY_CNT_STR] if os.environ.get(BATTERY_NOTIFY_CNT_STR) else '0'
                os.environ[BATTERY_THRESHOLD_NOTIFY_CNT_STR] = os.environ[BATTERY_THRESHOLD_NOTIFY_CNT_STR] if os.environ.get(BATTERY_THRESHOLD_NOTIFY_CNT_STR) else '0'

                is_threshold = False
                try:
                    # default fallback: ~3 hours before capping (6 minutes per battery, so 30 battery for ~3 hours)
                    battery_threshold = int(config.GENSHINPY_ZZZ.get('battery_threshold') or -30)
                    if battery_threshold < 0:
                        is_threshold = notes.battery_charge.current >= (notes.battery_charge.max + battery_threshold)
                    else:
                        is_threshold = notes.battery_charge.current >= battery_threshold
                except:
                    pass

                is_battery_notify = int(os.environ[BATTERY_NOTIFY_CNT_STR]) <= config.FULL_STAMINA_REPEAT_NOTIFY
                is_battery_threshold_notify = int(os.environ[BATTERY_THRESHOLD_NOTIFY_CNT_STR]) < 1
                is_battery_recovery_time_changed = False
                os.environ[BATTERY_LAST_RECOVERY_TIME] = os.environ[BATTERY_LAST_RECOVERY_TIME] if os.environ.get(BATTERY_LAST_RECOVERY_TIME) else str(notes.battery_charge.full_datetime.timestamp())
                is_battery_recovery_time_changed = abs(float(os.environ[BATTERY_LAST_RECOVERY_TIME]) - notes.battery_charge.full_datetime.timestamp()) > 400

                if is_full and is_battery_notify:
                    os.environ[BATTERY_NOTIFY_CNT_STR] = str(int(os.environ[BATTERY_NOTIFY_CNT_STR]) + 1)
                    status = f'Battery Charge is full! ({os.environ[BATTERY_NOTIFY_CNT_STR]}/{config.FULL_STAMINA_REPEAT_NOTIFY + 1})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_threshold and is_battery_threshold_notify:
                    status = 'Battery Charge is almost full!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                    os.environ[BATTERY_THRESHOLD_NOTIFY_CNT_STR] = str(int(os.environ[BATTERY_THRESHOLD_NOTIFY_CNT_STR]) + 1)
                elif is_battery_recovery_time_changed and not is_full:
                    status = 'Battery Charge\'s recovery time has changed!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_first_run:
                    status = 'Real-Time Notes is being monitored!'
                    os.environ[IS_NOTIFY_STR] = 'True'

                os.environ[BATTERY_NOTIFY_CNT_STR] = os.environ[BATTERY_NOTIFY_CNT_STR] if is_full else '0'
                os.environ[BATTERY_THRESHOLD_NOTIFY_CNT_STR] = os.environ[BATTERY_THRESHOLD_NOTIFY_CNT_STR] if is_threshold else '0'
                os.environ[BATTERY_LAST_RECOVERY_TIME] = str(notes.battery_charge.full_datetime.timestamp())

                title = status
                log.info(title)
                if os.environ[IS_NOTIFY_STR] == 'True':
                    notify_me(title, content)
        except genshin.GenshinException as e:
            log.info(e)
        except Exception as e:
            log.exception('EXCEPTION')
        finally:
            log.info('Task finished.')
    return result


def schedulecatch(func):
    try:
        asyncio.get_event_loop().run_until_complete(func())
    except Exception as e:
        print(e)


async def all_job2():
    if config.GENSHINPY.get('cookies') and not config.GENSHINPY.get('skip_notes'):
        await job2genshinpy()
    if config.GENSHINPY_STARRAIL.get('cookies') and not config.GENSHINPY_STARRAIL.get('skip_notes'):
        await job2genshinpystarrail()
    if config.GENSHINPY_ZZZ.get('cookies') and not config.GENSHINPY_ZZZ.get('skip_notes'):
        await job2genshinpyzzz()


async def run_once():
    try:
        for i in dict(os.environ):
            if 'UID_' in i:
                del os.environ[i]

        await all_job2()
        await job1()
    except Exception as e:
        print(e)


async def main():
    log.info(banner)

    gh.set_lang(config.LANGUAGE)

    await run_once()

    # schedule all_job2()
    if config.CHECK_NOTES_SECS_RANGE:
        t1, t2 = config.CHECK_NOTES_SECS_RANGE.split('-')
        schedule.every(int(t1)).to(int(t2)).seconds.do(lambda: schedulecatch(all_job2))
    else:
        schedule.every(int(config.CHECK_NOTES_SECS)).seconds.do(lambda: schedulecatch(all_job2))

    # schedule job1()
    schedule.every().day.at(config.CHECK_IN_TIME).do(lambda: schedulecatch(job1))

    while True:
        await asyncio.sleep(1)
        schedule.run_pending()


if __name__ == '__main__':
    asyncio.run(main())
