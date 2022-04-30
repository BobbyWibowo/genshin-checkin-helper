"""
@Project   : genshinhelper
@Author    : y1ndan
@Blog      : https://www.yindan.me
@GitHub    : https://github.com/y1ndan
"""

from collections.abc import Iterable
from inspect import iscoroutinefunction
from math import ceil
# from pprint import pprint
from random import randint
from time import sleep
import datetime
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

import nest_asyncio
nest_asyncio.apply()

version = '1.0.3-genshin.py'
banner = f'''
+----------------------------------------------------------------+
|         𒆙  Genshin Check-In Helper v{version}           |
+----------------------------------------------------------------+
Project      : genshinhelper
Description  : More than check-in for Genshin Impact.
PKG_Version  : {gh.__version__}
genshin.py   : {genshin.__version__}
Author       : 银弹GCell(y1ndan)
Blog         : https://www.yindan.me
Channel      : https://t.me/genshinhelperupdates
------------------------------------------------------------------'''


def random_sleep(interval: str):
    seconds = randint(*[int(i) for i in interval.split('-')])
    log.info('Sleeping for {seconds}s...'.format(seconds=seconds))
    sleep(seconds)


def time_in_range(interval: str):
    t1, t2 = interval.split('-')
    now_time = datetime.datetime.now().time()
    start = datetime.datetime.strptime(t1, '%H:%M').time()
    end = datetime.datetime.strptime(t2, '%H:%M').time()
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

    timezone = datetime.timezone(datetime.timedelta(hours=display_utc_offset))
    utc_offset_str = f"UTC{'+' if display_utc_offset >= 0 else ''}{display_utc_offset}"
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
            log.info(f"Could not find account matching UID {_uid}.")

    if got_accounts:
        return got_accounts
    else:
        log.info(f"Could not find any account matching UIDs {uids}.")
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


def display_time(time, short=False):
    if type(time) != dict:
        raise ValueError('Input type must be a dict')

    order = ('day', 'hour', 'minute', 'second')
    result = []
    for i, name in enumerate(order):
        value = time[name]
        if type(value) == int and value > 0:
            prepend = 'and ' if i == len(order) - 1 and result else ''
            unit = name[0] if short else (name + 's' if value != 1 else '')
            result.append('{}{} {}'.format(prepend, value, unit))
    return ' '.join(result)


def task_common(r, d, text_temp1, text_temp2):
    result = []
    for i in range(len(r)):
        if d and d[i]:
            d[i]['month'] = gh.month()
            r[i]['addons'] = text_temp2.format(**d[i])
        message = text_temp1.format(**r[i])
        result.append(message)
    return result


def task1(cookie):
    t = gh.Genshin(cookie)
    r = t.sign()
    d = t.month_dairy
    return task_common(r, d, MESSAGE_TEMPLATE, DAIRY_TEMPLATE)


def task2(cookie):
    t = gh.YuanShen(cookie)
    r = t.sign()
    d = t.month_dairy
    return task_common(r, d, MESSAGE_TEMPLATE, DAIRY_TEMPLATE)


def task3(cookie):
    t = gh.Honkai3rd(cookie)
    r = t.sign()
    d = t.month_finance
    return task_common(r, d, MESSAGE_TEMPLATE, FINANCE_TEMPLATE)


def task4(cookie):
    t = gh.MysDailyMissions(cookie)
    r = t.run(26)
    total_points = r['total_points']
    is_sign = r['is_sign']
    is_view = r['is_view']
    is_upvote = r['is_upvote']
    is_share = r['is_share']

    result_str = '''米游币: {}
    签到: {}
    浏览: {}
    点赞: {}
    分享: {}'''.format(total_points, is_sign, is_view, is_upvote, is_share)
    return [result_str]


def task5(cookie):
    r = gh.get_cloudgenshin_free_time(cookie)
    message = nested_lookup(r, 'message', fetch_first=True)
    free_time = nested_lookup(r, 'free_time', fetch_first=True)
    if not free_time:
        pass
    free_time = free_time['free_time']
    free_time_limit = nested_lookup(r, 'free_time_limit', fetch_first=True)
    total_time = nested_lookup(r, 'total_time', fetch_first=True)
    free_time_fmt = '{hour}时{minute}分'.format(**(minutes_to_hours(free_time)))
    free_time_limit_fmt = '{hour}时{minute}分'.format(
        **minutes_to_hours(free_time_limit))
    total_time_fmt = '{hour}时{minute}分'.format(**minutes_to_hours(total_time))

    result_str = '''签到结果: {}
    免费时长: {} / {}
    总计时长: {}'''.format(message, free_time_fmt, free_time_limit_fmt, total_time_fmt)
    return result_str


def task6(cookie):
    t = gh.Weibo(params=cookie)
    r = t.sign()
    result = []
    for i in r:
        lv = i['level']
        name = i['name']
        is_sign = i['is_sign']
        response = i.get('sign_response')

        status = response
        if is_sign and not response:
            status = '☑️'
        if is_sign and response:
            status = '✅'

        message = f'⚜️ [Lv.{lv}]{name} {status}\n    '
        result.append(message)
    return result


def task7(cookie):
    t = gh.Weibo(cookie=cookie)
    is_event = t.check_event()
    if not is_event:
        return '原神超话现在没有活动哦'

    title = '原神超话签到提醒'
    content = '亲爱的旅行者, 原神微博超话签到活动现已开启, 请注意活动时间! 如已完成任务, 请忽略本信息.'
    notify_me(title, content)
    ids = t.unclaimed_gift_ids()
    if not ids:
        recent_codes = ' *'.join(
            [f"{i['title']} {i['code']}" for i in t.get_mybox_codes()[:3]])
        return f'原神超话签到活动已开启，但是没有未领取的兑换码。\n    最近 3 个码: {recent_codes}'

    log.info(f'检测到有 {len(ids)} 个未领取的兑换码')
    raw_codes = [t.get_code(id) for id in ids]
    return [str(i['code'] + '\n    ') if i['success'] else str(i['response']['msg'] + '\n    ') for i in raw_codes]


def task8(cookie):
    is_sign = gh.check_jfsc(cookie)
    result = '今天已经签到, 请明天再来'
    if not is_sign:
        r = gh.sign_jfsc(cookie)
        result = r.get('msg')
    return result

async def taskgenshinpy(cookie):
    try:
        result = []

        client = genshin.Client(game=genshin.Game.GENSHIN)
        client.set_cookies(cookie)

        log.info('Preparing to get user game roles information...')
        accounts = list(filter(lambda account: 'hk4e' in account.game_biz, await client.get_game_accounts()))
        if not accounts:
            return log.info("There are no Genshin accounts associated to this HoYoverse account.")

        DIARY_TEMPLATE = '''    Traveler's Diary: {month}
    💠 Primogems: {current_primogems}
    🌕 Mora: {current_mora}'''

        CLAIM_TEMPLATE = '''    Today's reward: {name} x {amount}
    Total monthly check-ins: {claimed_rewards} day(s)
    Status: {status}
'''

        got_accounts = None
        if config.GENSHINPY.get('uids'):
            uids = config.GENSHINPY.get('uids').split('#')
            got_accounts = get_genshinpy_accounts(accounts, uids)
            if not got_accounts:
                return
        else:
            got_accounts = accounts

        date_appended = False
        for account in got_accounts:
            message = ''
            if not date_appended or type(config.GENSHINPY.get('utc_offset')) != int:
                timezone, utc_offset_str = assert_timezone(server=account.server)
                today = f"{datetime.datetime.now(timezone).strftime('%Y-%m-%d %I:%M %p')} {utc_offset_str}" if timezone else 'N/A'
                message += f'📅 {today}\n'
                date_appended = True
            message += f'🔅 {account.nickname} {account.server_name} Lv. {account.level}\n'
            result.append(message)

        data = {}
        try:
            log.info('Preparing to claim daily reward...')
            reward = await client.claim_daily_reward()
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

        log.info('Preparing to get monthly rewards information...')
        reward_info = await client.get_reward_info()
        data['claimed_rewards'] = reward_info.claimed_rewards
        claim_message = CLAIM_TEMPLATE.format(**data)
        result.append(claim_message)

        log.info('Preparing to get traveler\'s diary...')
        diary = await client.get_diary()
        diary_data = {
            'month': datetime.datetime.strptime(str(diary.month), "%m").strftime("%B"),
            'current_primogems': diary.data.current_primogems,
            'current_mora': diary.data.current_mora
        }
        daily_addons = DIARY_TEMPLATE.format(**diary_data)
        result.append(daily_addons)
    finally:
        # await client.close()
        log.info('Task finished.')
    return result

async def taskgenshinpyhonkai(cookie):
    try:
        result = []

        client = genshin.Client(game=genshin.Game.HONKAI)
        client.set_cookies(cookie)

        log.info('Preparing to get user game roles information...')
        accounts = list(filter(lambda account: 'bh3' in account.game_biz, await client.get_game_accounts()))
        if not accounts:
            return log.info("There are no Honkai accounts associated to this HoYoverse account.")

        CLAIM_TEMPLATE = '''    Today's reward: {name} x {amount}
    Total monthly check-ins: {claimed_rewards} day(s)
    Status: {status}'''

        got_accounts = None
        if config.GENSHINPY_HONKAI.get('uids'):
            uids = config.GENSHINPY_HONKAI.get('uids').split('#')
            got_accounts = get_genshinpy_accounts(accounts, uids)
            if not got_accounts:
                return
        else:
            got_accounts = accounts

        date_appended = False
        for account in got_accounts:
            message = ''
            if not date_appended or type(config.GENSHINPY_HONKAI.get('utc_offset')) != int:
                timezone, utc_offset_str = assert_timezone(server=account.server, conf=config.GENSHINPY_HONKAI)
                today = f"{datetime.datetime.now(timezone).strftime('%Y-%m-%d %I:%M %p')} {utc_offset_str}" if timezone else 'N/A'
                message += f'📅 {today}\n'
                date_appended = True
            message += f'🔅 {account.nickname} {account.server_name} Lv. {account.level}\n'
            result.append(message)

        data = {}
        try:
            log.info('Preparing to claim daily reward...')
            reward = await client.claim_daily_reward()
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
    finally:
        # await client.close()
        log.info('Task finished.')
    return result

task_list = [{
    'name': 'HoYoLAB Community',
    'cookies': get_cookies(config.COOKIE_HOYOLAB),
    'function': task1
}, {
    'name': '原神签到福利',
    'cookies': get_cookies(config.COOKIE_MIHOYOBBS),
    'function': task2
}, {
    'name': '崩坏3福利补给',
    'cookies': get_cookies(config.COOKIE_BH3),
    'function': task3
}, {
    'name': '米游币签到姬',
    'cookies': get_cookies(config.COOKIE_MIYOUBI),
    'function': task4
}, {
    'name': '云原神签到姬',
    'cookies': get_cookies(config.CLOUD_GENSHIN),
    'function': task5
}, {
    'name': '微博超话签到',
    'cookies': get_cookies(config.COOKIE_WEIBO),
    'function': task6
}, {
    'name': '原神超话监测',
    'cookies': get_cookies(config.COOKIE_KA),
    'function': task7
}, {
    'name': '微信积分商城',
    'cookies': get_cookies(config.SHOPTOKEN),
    'function': task8
}, {
    'name': 'thesadru/genshin.py',
    'cookies': get_cookies(config.GENSHINPY.get('cookies')),
    'function': taskgenshinpy
}, {
    'name': 'thesadru/genshin.py-honkai',
    'cookies': get_cookies(config.GENSHINPY_HONKAI.get('cookies')),
    'function': taskgenshinpyhonkai
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
            result_str = "".join(raw_result) if isinstance(raw_result, Iterable) else raw_result
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
        title = f'Genshin Impact Helper ✅ {total_success_cnt} · ❎ {total_failure_cnt}'
        is_markdown = config.ONEPUSH.get('params', {}).get('markdown')
        content = f'```\n{message_box}```' if is_markdown else message_box
        notify_me(title, content)

    log.info('Finished daily check-in tasks.')


def job2():
    log.info('Starting real-time notes tasks...')
    result = []
    for i in get_cookies(config.COOKIE_RESIN_TIMER):
        ys = gh.YuanShen(i)
        roles_info = ys.roles_info
        expedition_fmt = '└─ {character_name:<8} {status_:^8} {remained_time_fmt}\n'
        RESIN_TIMER_TEMPLATE = '''实时便笺
    🔅{nickname} {level} {region_name}
    原粹树脂: {current_resin} / {max_resin} {resin_recovery_datetime_fmt}
    今日委托: {finished_task_num} / {total_task_num}
    周本减半: {remain_resin_discount_num} / {resin_discount_num_limit}
    探索派遣: {current_expedition_num} / {max_expedition_num}
      {expedition_details}'''

        for i in roles_info:
            daily_note = ys.get_daily_note(i['game_uid'], i['region'])
            if not daily_note:
                log.info(f"未能获取 {i['nickname']} 的实时便笺, 正在跳过...")
                continue

            details = []
            for e in daily_note['expeditions']:
                remained_time = int(e['remained_time'])
                e['remained_time_fmt'] = '{hour}小时{minute}分钟'.format(**minutes_to_hours(remained_time / 60)) if remained_time else ''
                e['character_name'] = e['avatar_side_icon'].split('Side_')[1].split('.')[0]
                e['status_'] = '剩余时间' if e['status'] == 'Ongoing' else '探险完成'
                details.append(expedition_fmt.format(**e))

            daily_note.update(i)
            resin_recovery_time = int(daily_note['resin_recovery_time'])
            resin_recovery_datetime = datetime.datetime.now() + datetime.timedelta(seconds=resin_recovery_time)
            daily_note['resin_recovery_datetime_fmt'] = f"将于{resin_recovery_datetime.strftime('%Y-%m-%d %H:%M:%S')}全部恢复" if resin_recovery_time else '原粹树脂已全部恢复, 记得及时使用哦'
            daily_note['expedition_details'] = '      '.join(details)
            message = RESIN_TIMER_TEMPLATE.format(**daily_note)
            result.append(message)
            log.info(message)

            is_markdown = config.ONEPUSH.get('params', {}).get('markdown')
            content = f'```\n{message}```' if is_markdown else message
            status = '未满足推送条件, 监控模式运行中...'

            count = 5
            IS_NOTIFY_STR = f"UID_{i['game_uid']}_IS_NOTIFY_STR"
            RESIN_NOTIFY_CNT_STR = f"UID_{i['game_uid']}_RESIN_NOTIFY_CNT"
            RESIN_THRESHOLD_NOTIFY_CNT_STR = f"UID_{i['game_uid']}_RESIN_THRESHOLD_NOTIFY_CNT"
            RESIN_LAST_RECOVERY_TIME = f"UID_{i['game_uid']}_RESIN_LAST_RECOVERY_TIME"
            EXPEDITION_NOTIFY_CNT_STR = f"UID_{i['game_uid']}_EXPEDITION_NOTIFY_CNT"
            os.environ[IS_NOTIFY_STR] = 'False'
            os.environ[RESIN_NOTIFY_CNT_STR] = os.environ[RESIN_NOTIFY_CNT_STR] if os.environ.get(RESIN_NOTIFY_CNT_STR) else '0'
            os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] = os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] if os.environ.get(RESIN_THRESHOLD_NOTIFY_CNT_STR) else '0'
            os.environ[EXPEDITION_NOTIFY_CNT_STR] = os.environ[EXPEDITION_NOTIFY_CNT_STR] if os.environ.get(EXPEDITION_NOTIFY_CNT_STR) else '0'
            os.environ[RESIN_LAST_RECOVERY_TIME] = os.environ[RESIN_LAST_RECOVERY_TIME] if os.environ.get(RESIN_LAST_RECOVERY_TIME) else str(resin_recovery_datetime.timestamp())

            is_full = daily_note['current_resin'] >= daily_note['max_resin']
            is_threshold = daily_note['current_resin'] >= int(config.RESIN_THRESHOLD)
            is_resin_notify = int(os.environ[RESIN_NOTIFY_CNT_STR]) < count
            is_resin_threshold_notify = int(os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR]) < 1
            is_do_not_disturb = time_in_range(config.RESIN_TIMER_DO_NOT_DISTURB)
            is_resin_recovery_time_changed = abs(float(os.environ[RESIN_LAST_RECOVERY_TIME]) - resin_recovery_datetime.timestamp()) > 400

            if is_full and is_resin_notify and not is_do_not_disturb:
                status = '原粹树脂回满啦!'
                os.environ[IS_NOTIFY_STR] = 'True'
                os.environ[RESIN_NOTIFY_CNT_STR] = str(int(os.environ[RESIN_NOTIFY_CNT_STR]) + 1)
            elif is_threshold and is_resin_threshold_notify and not is_do_not_disturb:
                status = '原粹树脂快满啦!'
                os.environ[IS_NOTIFY_STR] = 'True'
                os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] = str(int(os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR]) + 1)
            elif is_resin_recovery_time_changed:
                status = '原粹树脂恢复时间变动啦!'
                os.environ[IS_NOTIFY_STR] = 'True'
            elif 'Finished' in str(daily_note['expeditions']) and int(os.environ[EXPEDITION_NOTIFY_CNT_STR]) < count and not is_do_not_disturb:
                status = '探索派遣完成啦!'
                os.environ[IS_NOTIFY_STR] = 'True'
                os.environ[EXPEDITION_NOTIFY_CNT_STR] = str(int(os.environ[EXPEDITION_NOTIFY_CNT_STR]) + 1)

            os.environ[RESIN_NOTIFY_CNT_STR] = os.environ[RESIN_NOTIFY_CNT_STR] if is_full else '0'
            os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] = os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] if is_threshold else '0'
            os.environ[EXPEDITION_NOTIFY_CNT_STR] = os.environ[EXPEDITION_NOTIFY_CNT_STR] if 'Finished' in str(daily_note['expeditions']) else '0'
            os.environ[RESIN_LAST_RECOVERY_TIME] = str(resin_recovery_datetime.timestamp())

            title = f'原神签到小助手提醒您: {status}'
            log.info(title)
            if os.environ[IS_NOTIFY_STR] == 'True':
                notify_me(title, content)
    return result

async def job2genshinpy():
    log.info('Starting real-time notes tasks using 「thesadru/genshin.py」...')
    result = []
    for i in get_cookies(config.GENSHINPY.get('cookies')):
        try:
            client = genshin.Client(game=genshin.Game.GENSHIN)
            client.set_cookies(i)

            log.info('Preparing to get user game roles information...')
            accounts = list(filter(lambda account: 'hk4e' in account.game_biz, await client.get_game_accounts()))
            if not accounts:
                return log.info("There are no Genshin accounts associated to this HoYoverse account.")

            expedition_fmt = '└─ {character_name:<10} {expedition_status}'
            RESIN_TIMER_TEMPLATE = '''🏆 thesadru/genshin.py
☁️ Real-Time Notes
📅 {today}
🔅 {nickname} {server_name} Lv. {level}
    Original Resin: {current_resin} / {max_resin} {until_resin_recovery_fmt}
     └─ {until_resin_recovery_date_fmt}
    Realm Currency: {realm_currency}
    Daily Commissions: {completed_commissions} / {max_commissions} {commissions_status}
    Enemies of Note: {remaining_resin_discounts} / {max_resin_discounts} {resin_discounts_status}
    Parametric Transformer: {transformer}
    Expedition Limit: {completed_expeditions} / {max_expeditions}'''

            REALM_CURRENCY_TEMPLATE = '''{current_realm_currency} / {max_realm_currency} {until_realm_currency_recovery_fmt}
     └─ {until_realm_currency_recovery_date_fmt}'''

            TRANSFORMER_TEMPLATE = '''{until_transformer_recovery_fmt}
     └─ {until_transformer_recovery_date_fmt}'''

            got_accounts = None
            if config.GENSHINPY.get('uids'):
                uids = config.GENSHINPY.get('uids').split('#')
                got_accounts = get_genshinpy_accounts(accounts, uids)
                if not got_accounts:
                    return
            else:
                got_accounts = accounts

            for account in got_accounts:
                log.info(f"Preparing to get notes information for UID {account.uid}...")
                notes = await client.get_notes(account.uid)

                timezone, utc_offset_str = assert_timezone(server=account.server)
                data = {
                    'today': f"{datetime.datetime.now(tz=timezone).strftime('%Y-%m-%d %I:%M %p')} {utc_offset_str}" if timezone else '',
                    'nickname': account.nickname,
                    'server_name': account.server_name,
                    'level': account.level,
                    'current_resin': notes.current_resin,
                    'max_resin': notes.max_resin,
                    'until_resin_recovery_fmt': '',
                    'current_realm_currency': notes.current_realm_currency,
                    'max_realm_currency': notes.max_realm_currency,
                    'until_realm_currency_recovery_fmt': '',
                    'completed_commissions': notes.completed_commissions,
                    'max_commissions': notes.max_commissions,
                    'commissions_status': '⚠️' if notes.completed_commissions < notes.max_commissions else '',
                    'remaining_resin_discounts': notes.remaining_resin_discounts,
                    'max_resin_discounts': notes.max_resin_discounts,
                    'resin_discounts_status': '⚠️' if notes.remaining_resin_discounts > 0 else '',
                    'completed_expeditions': 0,
                    'max_expeditions': notes.max_expeditions
                }

                details = []
                earliest_expedition = False
                for expedition in notes.expeditions:
                    expedition_data = { 'character_name': expedition.character.name }
                    if expedition.finished:
                        expedition_data['expedition_status'] = '✨ Completed!'
                        data['completed_expeditions'] += 1
                    else:
                        remaining_time = max((expedition.completion_time.replace(tzinfo=None) - datetime.datetime.now()).total_seconds(), 0)
                        expedition_data['expedition_status'] = '({hour} h and {minute} min)'.format(**minutes_to_hours(remaining_time / 60))
                        if not earliest_expedition or expedition.completion_time < earliest_expedition:
                            earliest_expedition = expedition.completion_time
                    details.append(expedition_fmt.format(**expedition_data))

                if earliest_expedition:
                    if timezone:
                        details.append(f"└─ Earliest at {earliest_expedition.astimezone(tz=timezone).strftime('%Y-%m-%d %I:%M %p')} {utc_offset_str}")
                    else:
                        details.append(f"└─ Earliest at {earliest_expedition.strftime('%Y-%m-%d %I:%M %p')}")

                is_full = notes.current_resin >= notes.max_resin
                is_resin_recovery_time_datetime = isinstance(notes.resin_recovery_time, datetime.datetime)
                if not is_full and is_resin_recovery_time_datetime:
                    until_resin_recovery = (notes.resin_recovery_time.replace(tzinfo=None) - datetime.datetime.now(tz=None)).total_seconds()
                    data['until_resin_recovery_fmt'] = "({hour} h and {minute} min)".format(**minutes_to_hours(until_resin_recovery / 60))
                    if timezone:
                        data['until_resin_recovery_date_fmt'] = f"Full at {notes.resin_recovery_time.astimezone(tz=timezone).strftime('%Y-%m-%d %I:%M %p')} {utc_offset_str}"
                    else:
                        data['until_resin_recovery_date_fmt'] = f"Full at {notes.resin_recovery_time.strftime('%Y-%m-%d %I:%M %p')}"
                else:
                    data['until_resin_recovery_date_fmt'] = '✨ Full!'

                do_realm_currency = bool(notes.max_realm_currency)
                is_realm_currency_full = is_realm_currency_recovery_time_datetime = False
                if do_realm_currency:
                    is_realm_currency_full = notes.current_realm_currency >= notes.max_realm_currency
                    is_realm_currency_recovery_time_datetime = isinstance(notes.realm_currency_recovery_time, datetime.datetime)
                    if not is_realm_currency_full and is_realm_currency_recovery_time_datetime:
                        until_realm_currency_recovery = (notes.realm_currency_recovery_time.replace(tzinfo=None) - datetime.datetime.now(tz=None)).total_seconds()
                        data['until_realm_currency_recovery_fmt'] = "({hour} h and {minute} min)".format(**minutes_to_hours(until_realm_currency_recovery / 60))
                        if timezone:
                            data['until_realm_currency_recovery_date_fmt'] = f"Full at {notes.realm_currency_recovery_time.astimezone(tz=timezone).strftime('%Y-%m-%d %I:%M %p')} {utc_offset_str}"
                        else:
                            data['until_realm_currency_recovery_date_fmt'] = f"Full at {notes.realm_currency_recovery_time.strftime('%Y-%m-%d %I:%M %p')}"
                    else:
                        data['until_realm_currency_recovery_date_fmt'] = '✨ Full!'
                    data['realm_currency'] = REALM_CURRENCY_TEMPLATE.format(**data)
                else:
                    data['realm_currency'] = 'N/A'

                do_transformer = notes.remaining_transformer_recovery_time != None
                is_transformer_ready = until_transformer_recovery = False
                if do_transformer:
                    until_transformer_recovery = ceil((notes.transformer_recovery_time.replace(tzinfo=None) - datetime.datetime.now(tz=None)).total_seconds())
                    if until_transformer_recovery > 0:
                        until_transformer_recovery_time = seconds_to_time(until_transformer_recovery)
                        recovery_date_fmt = '%Y-%m-%d'
                        if type(until_transformer_recovery_time['hour']) == int and until_transformer_recovery_time['hour'] > 0:
                            if type(until_transformer_recovery_time['minute']) == int and until_transformer_recovery_time['minute'] > 0:
                                recovery_date_fmt += ' %I:%M %p'
                            else:
                                recovery_date_fmt += ' %I:00 %p'
                        if timezone:
                            data['until_transformer_recovery_date_fmt'] = f"Ready at {notes.transformer_recovery_time.astimezone(tz=timezone).strftime(recovery_date_fmt)} {utc_offset_str}"
                        else:
                            data['until_transformer_recovery_date_fmt'] = f"Ready at {notes.transformer_recovery_time.strftime(recovery_date_fmt)}"
                        data['until_transformer_recovery_fmt'] = display_time(until_transformer_recovery_time, True)
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
                result.append(message)
                log.info(message)

                is_markdown = config.ONEPUSH.get('params', {}).get('markdown')
                content = f'```\n{message}```' if is_markdown else message
                status = 'Push conditions have not been met yet, will re-check later as scheduled.'

                count = 5
                IS_NOTIFY_STR = f"UID_{account.uid}_IS_NOTIFY_STR"
                RESIN_NOTIFY_CNT_STR = f"UID_{account.uid}_RESIN_NOTIFY_CNT"
                RESIN_THRESHOLD_NOTIFY_CNT_STR = f"UID_{account.uid}_RESIN_THRESHOLD_NOTIFY_CNT"
                RESIN_LAST_RECOVERY_TIME = f"UID_{account.uid}_RESIN_LAST_RECOVERY_TIME"
                REALM_CURRENCY_NOTIFY_CNT_STR = f"UID_{account.uid}_REALM_CURRENCY_NOTIFY_CNT"
                REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR = f"UID_{account.uid}_REALM_CURRENCY_THRESHOLD_NOTIFY_CNT"
                REALM_CURRENCY_LAST_RECOVERY_TIME = f"UID_{account.uid}_REALM_CURRENCY_LAST_RECOVERY_TIME"
                TRANSFORMER_NOTIFY_CNT_STR = f"UID_{account.uid}_TRANSFORMER_NOTIFY_CNT"
                TRANSFORMER_LAST_RECOVERY_TIME = f"UID_{account.uid}_TRANSFORMER_LAST_RECOVERY_TIME"
                EXPEDITION_NOTIFY_CNT_STR = f"UID_{account.uid}_EXPEDITION_NOTIFY_CNT"

                is_first_run = not bool(os.environ.get(IS_NOTIFY_STR))
                os.environ[IS_NOTIFY_STR] = 'False'
                os.environ[RESIN_NOTIFY_CNT_STR] = os.environ[RESIN_NOTIFY_CNT_STR] if os.environ.get(RESIN_NOTIFY_CNT_STR) else '0'
                os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] = os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] if os.environ.get(RESIN_THRESHOLD_NOTIFY_CNT_STR) else '0'
                os.environ[EXPEDITION_NOTIFY_CNT_STR] = os.environ[EXPEDITION_NOTIFY_CNT_STR] if os.environ.get(EXPEDITION_NOTIFY_CNT_STR) else '0'

                is_threshold = notes.current_resin >= int(config.RESIN_THRESHOLD)
                is_resin_notify = int(os.environ[RESIN_NOTIFY_CNT_STR]) < count
                is_resin_threshold_notify = int(os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR]) < 1
                is_resin_recovery_time_changed = False
                if is_resin_recovery_time_datetime:
                    os.environ[RESIN_LAST_RECOVERY_TIME] = os.environ[RESIN_LAST_RECOVERY_TIME] if os.environ.get(RESIN_LAST_RECOVERY_TIME) else str(notes.resin_recovery_time.timestamp())
                    is_resin_recovery_time_changed = abs(float(os.environ[RESIN_LAST_RECOVERY_TIME]) - notes.resin_recovery_time.timestamp()) > 400
                is_any_expedition_completed = data['completed_expeditions'] > 0

                is_realm_currency_threshold = is_realm_currency_notify = is_realm_currency_threshold_notify = is_realm_currency_recovery_time_changed = False
                if do_realm_currency:
                    os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] = os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] if os.environ.get(REALM_CURRENCY_NOTIFY_CNT_STR) else '0'
                    os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] = os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] if os.environ.get(REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR) else '0'
                    try:
                        realm_currency_threshold = int(config.GENSHINPY.get('realm_currency_threshold'))
                        if realm_currency_threshold < 0:
                            is_realm_currency_threshold = notes.current_realm_currency >= (notes.max_realm_currency + realm_currency_threshold)
                        else:
                            is_realm_currency_threshold = notes.current_realm_currency >= realm_currency_threshold
                    except:
                        pass
                    is_realm_currency_notify = int(os.environ[REALM_CURRENCY_NOTIFY_CNT_STR]) < count
                    is_realm_currency_threshold_notify = int(os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR]) < 1
                    if is_realm_currency_recovery_time_datetime:
                        os.environ[REALM_CURRENCY_LAST_RECOVERY_TIME] = os.environ[REALM_CURRENCY_LAST_RECOVERY_TIME] if os.environ.get(REALM_CURRENCY_LAST_RECOVERY_TIME) else str(notes.realm_currency_recovery_time.timestamp())
                        is_realm_currency_recovery_time_changed = abs(float(os.environ[REALM_CURRENCY_LAST_RECOVERY_TIME]) - notes.realm_currency_recovery_time.timestamp()) > 400

                is_transformer_notify = is_transformer_recovery_time_changed = False
                if do_transformer:
                    os.environ[TRANSFORMER_NOTIFY_CNT_STR] = os.environ[TRANSFORMER_NOTIFY_CNT_STR] if os.environ.get(TRANSFORMER_NOTIFY_CNT_STR) else '0'
                    is_transformer_notify = int(os.environ[TRANSFORMER_NOTIFY_CNT_STR]) < count
                    if until_transformer_recovery:
                        os.environ[TRANSFORMER_LAST_RECOVERY_TIME] = os.environ[TRANSFORMER_LAST_RECOVERY_TIME] if os.environ.get(TRANSFORMER_LAST_RECOVERY_TIME) else str(until_transformer_recovery)
                        is_transformer_recovery_time_changed = int(os.environ[TRANSFORMER_LAST_RECOVERY_TIME]) < until_transformer_recovery

                is_do_not_disturb = time_in_range(config.RESIN_TIMER_DO_NOT_DISTURB)

                if is_full and is_resin_notify and not is_do_not_disturb:
                    os.environ[RESIN_NOTIFY_CNT_STR] = str(int(os.environ[RESIN_NOTIFY_CNT_STR]) + 1)
                    status = f'Original Resin is full! ({os.environ[RESIN_NOTIFY_CNT_STR]}/{count})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_threshold and is_resin_threshold_notify and not is_do_not_disturb:
                    status = 'Original Resin is almost full!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                    os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] = str(int(os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR]) + 1)
                elif is_resin_recovery_time_changed and not is_full:
                    status = 'Original Resin\'s recovery time has changed!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_realm_currency_full and is_realm_currency_notify and not is_do_not_disturb:
                    os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] = str(int(os.environ[REALM_CURRENCY_NOTIFY_CNT_STR]) + 1)
                    status = f'Realm Currency is full! ({os.environ[REALM_CURRENCY_NOTIFY_CNT_STR]}/{count})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_realm_currency_threshold and is_realm_currency_threshold_notify and not is_do_not_disturb:
                    status = 'Realm Currency is almost full!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                    os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] = str(int(os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR]) + 1)
                elif is_realm_currency_recovery_time_changed and not is_realm_currency_full:
                    status = 'Realm Currency\'s recovery time has changed!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_transformer_ready and is_transformer_notify and not is_do_not_disturb:
                    os.environ[TRANSFORMER_NOTIFY_CNT_STR] = str(int(os.environ[TRANSFORMER_NOTIFY_CNT_STR]) + 1)
                    status = f'Parametric Transformer is ready! ({os.environ[TRANSFORMER_NOTIFY_CNT_STR]}/{count})'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_transformer_recovery_time_changed and not is_transformer_ready:
                    status = 'Parametric Transformer\'s recovery time has changed!'
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_any_expedition_completed and int(os.environ[EXPEDITION_NOTIFY_CNT_STR]) < count and not is_do_not_disturb:
                    os.environ[EXPEDITION_NOTIFY_CNT_STR] = str(int(os.environ[EXPEDITION_NOTIFY_CNT_STR]) + 1)
                    status = f"Expedition{'s' if data['completed_expeditions'] > 1 else ''} completed! ({os.environ[EXPEDITION_NOTIFY_CNT_STR]}/{count})"
                    os.environ[IS_NOTIFY_STR] = 'True'
                elif is_first_run:
                    status = 'Real-Time Notes is being monitored!'
                    os.environ[IS_NOTIFY_STR] = 'True'

                os.environ[RESIN_NOTIFY_CNT_STR] = os.environ[RESIN_NOTIFY_CNT_STR] if is_full else '0'
                os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] = os.environ[RESIN_THRESHOLD_NOTIFY_CNT_STR] if is_threshold else '0'
                if is_resin_recovery_time_datetime:
                    os.environ[RESIN_LAST_RECOVERY_TIME] = str(notes.resin_recovery_time.timestamp())
                os.environ[EXPEDITION_NOTIFY_CNT_STR] = os.environ[EXPEDITION_NOTIFY_CNT_STR] if is_any_expedition_completed else '0'

                if do_realm_currency:
                    os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] = os.environ[REALM_CURRENCY_NOTIFY_CNT_STR] if is_realm_currency_full else '0'
                    os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] = os.environ[REALM_CURRENCY_THRESHOLD_NOTIFY_CNT_STR] if is_realm_currency_threshold else '0'
                    if is_realm_currency_recovery_time_datetime:
                        os.environ[REALM_CURRENCY_LAST_RECOVERY_TIME] = str(notes.realm_currency_recovery_time.timestamp())

                if do_transformer:
                    os.environ[TRANSFORMER_NOTIFY_CNT_STR] = os.environ[TRANSFORMER_NOTIFY_CNT_STR] if is_transformer_ready else '0'
                    if until_transformer_recovery:
                        os.environ[TRANSFORMER_LAST_RECOVERY_TIME] = str(until_transformer_recovery)

                title = status
                log.info(title)
                if os.environ[IS_NOTIFY_STR] == 'True':
                    notify_me(title, content)
        except genshin.GenshinException as e:
            log.info(e)
        except Exception as e:
            log.exception('EXCEPTION')
        finally:
            # await client.close()
            log.info('Task finished.')
    return result


def schedulecatch(func):
    try:
        asyncio.get_event_loop().run_until_complete(func())
    except Exception as e:
        print(e)


async def run_once():
    try:
        for i in dict(os.environ):
            if 'UID_' in i:
                del os.environ[i]

        gh.set_lang(config.LANGUAGE)
        if config.COOKIE_RESIN_TIMER:
            job2()
        if config.GENSHINPY.get('cookies'):
            await job2genshinpy()
        await job1()
    except Exception as e:
        print(e)


async def main():
    log.info(banner)
    await run_once()

    schedule.every().day.at(config.CHECK_IN_TIME).do(lambda: schedulecatch(job1))

    if config.CHECK_RESIN_SECS_RANGE:
        t1, t2 = config.CHECK_RESIN_SECS_RANGE.split('-')
        if config.COOKIE_RESIN_TIMER:
            schedule.every(int(t1)).to(int(t2)).seconds.do(job2)
        if config.GENSHINPY.get('cookies'):
            schedule.every(int(t1)).to(int(t2)).seconds.do(lambda: schedulecatch(job2genshinpy))
    else:
        if config.COOKIE_RESIN_TIMER:
            schedule.every(int(config.CHECK_RESIN_SECS)).seconds.do(job2)
        if config.GENSHINPY.get('cookies'):
            schedule.every(int(config.CHECK_RESIN_SECS)).seconds.do(lambda: schedulecatch(job2genshinpy))

    while True:
        await asyncio.sleep(1)
        schedule.run_pending()


if __name__ == '__main__':
    asyncio.run(main())

