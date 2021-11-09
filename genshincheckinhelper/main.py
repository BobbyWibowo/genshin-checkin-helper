"""
@Project   : genshinhelper
@Author    : y1ndan
@Blog      : https://www.yindan.me
@GitHub    : https://github.com/y1ndan
"""

from collections.abc import Iterable
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

version = '1.0.3'
banner = f'''
+----------------------------------------------------------------+
|               𒆙  Genshin Check-In Helper v{version}                |
+----------------------------------------------------------------+
Project      : genshinhelper
Description  : More than check-in for Genshin Impact.
PKG_Version  : {gh.__version__}
Author       : 银弹GCell(y1ndan)
Blog         : https://www.yindan.me
Channel      : https://t.me/genshinhelperupdates
------------------------------------------------------------------'''


def random_sleep(interval: str):
    seconds = randint(*[int(i) for i in interval.split('-')])
    log.info('Sleep for {seconds} seconds...'.format(seconds=seconds))
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
        log.info('No notification method configured ...')
        return
    log.info('Preparing to send notification ...')
    return notify(notifier, title=title, content=content, **params)


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
}]


def run_task(name, cookies, func):
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
            raw_result = func(cookie)
            success_count += 1
        except Exception as e:
            raw_result = e
            log.exception('TRACEBACK')
            failure_count += 1
        finally:
            result_str = "".join(raw_result) if isinstance(raw_result, Iterable) else raw_result
            result_fmt = f'🌈 No.{i}:\n    {result_str}\n'
            result_list.append(result_fmt)
        continue

    task_name_fmt = f'🏆 {name}'
    status_fmt = f'☁️ ✔ {success_count} · ✖ {failure_count}'
    message_box = [success_count, failure_count, task_name_fmt, status_fmt, ''.join(result_list)]
    return message_box


def job1():
    log.info(banner)
    random_sleep(config.RANDOM_SLEEP_SECS_RANGE)
    log.info('Starting...')
    finally_result_dict = {
        i['name']: run_task(i['name'], i['cookies'], i['function'])
        for i in task_list
    }

    total_success_cnt = sum([i[0] for i in finally_result_dict.values()])
    total_failure_cnt = sum([i[1] for i in finally_result_dict.values()])
    message_list = sum([i[2::] for i in finally_result_dict.values()], [])
    tip = '\nWARNING: Please configure environment variables or config.json file first!\n'
    message_box = '\n'.join(message_list) if message_list else tip

    log.info('RESULT:\n' + message_box)
    if message_box != tip:
        title = f'Genshin Impact Helper ✔ {total_success_cnt} · ✖ {total_failure_cnt}'
        is_markdown = config.ONEPUSH.get('params', {}).get('markdown')
        content = f'```\n{message_box}```' if is_markdown else message_box
        notify_me(title, content)

    log.info('End of process run')


def job2():
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


def run_once():
    for i in dict(os.environ):
        if 'UID_' in i:
            del os.environ[i]

    gh.set_lang(config.LANGUAGE)
    job1()
    if config.COOKIE_RESIN_TIMER:
        job2()


def main():
    run_once()
    schedule.every().day.at(config.CHECK_IN_TIME).do(job1)
    if config.COOKIE_RESIN_TIMER:
        schedule.every(int(config.CHECK_RESIN_SECS)).seconds.do(job2)

    while True:
        schedule.run_pending()
        sleep(1)


if __name__ == '__main__':
    main()

