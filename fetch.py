import json
import re
import time
import requests
from requests import HTTPError

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import DesiredCapabilities
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


class document_is_loaded:
    def __call__(self, driver):
        state = driver.execute_script('return document.readyState')
        if state != 'complete':
            return False
        return state


class document_is_extended:
    def __init__(self, prev_height):
        self.prev_height = prev_height

    def __call__(self, driver):
        current_height = driver.execute_script('return document.body.scrollHeight')
        if current_height == self.prev_height:
            return False
        return current_height


capabilities = DesiredCapabilities.CHROME.copy()
capabilities["goog:loggingPrefs"] = {"performance": "ALL"}  # newer: goog:loggingPrefs
options = Options()
options.add_argument('--headless')
options.add_argument('--disable-gpu')


def main():
    driver = webdriver.Chrome(desired_capabilities=capabilities, options=options)

    driver.get('https://twitter.com/i/topics/857879016971186177')
    wait = WebDriverWait(driver, 10)
    driver.maximize_window()

    try:
        result = wait.until(document_is_loaded())
    except TimeoutException as TE:
        print("Unable to load document's content. Reasons are unknown")
        return
    while True:
        current_height_max = driver.execute_script('return document.body.scrollHeight')
        driver.execute_script(f'window.scrollTo(0, {current_height_max})')
        try:
            wait.until(document_is_extended(current_height_max))
        except TimeoutException as TE:
            print("Either all tweets are loaded or the rest couldn't be retrieved")
            break
        time.sleep(1)
    print('out of cycle')

    logs_raw = driver.get_log("performance")
    logs = [json.loads(lr['message'])['message'] for lr in logs_raw]
    tweets = []
    base_html_url = 'https://publish.twitter.com/oembed?url=https%3A%2F%2Ftwitter.com%2Faaditsh%2Fstatus%2F{' \
                    'tweet_id}&partner=&hide_thread=false'

    for log in logs:
        if log['method'] == 'Network.responseReceived' and "json" in log["params"]["response"]["mimeType"]:
            if re.match('.*TopicLandingPage.*', log['params']['response']['url']):
                text = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": log['params']['requestId']})
                # print(json.loads(text['body'])['data'])
                instructions = json.loads(text['body'])['data']['topic_by_rest_id']['topic_page']['body']['timeline']['instructions']
                for instr in instructions:
                    if instr.get('type') == 'TimelineAddEntries':
                        for entry in instr['entries']:
                            if item_content := entry['content'].get('itemContent'):
                                if item_content.get('itemType') == 'TimelineTweet':
                                    result = entry['content']['itemContent']['tweet_results']['result']
                                    if result['core']['user_results']['result']:
                                        tweet_info = dict()
                                        tweet_info['name'] = result['core']['user_results']['result']['legacy']['name']
                                        tweet_info['likes'] = result['legacy']['favorite_count']
                                        tweet_info['retweets'] = result['legacy']['retweet_count']
                                        tweet_info['replies'] = result['legacy']['reply_count']
                                        tweet_info['url'] = 'https://twitter.com/twitter/status/' + result['rest_id']
                                        retry_flag = False
                                        while True:
                                            try:
                                                request = requests.get(base_html_url.format(tweet_id=result['rest_id']))
                                                request.raise_for_status()
                                            except requests.exceptions.HTTPError:
                                                print('HTTPError. Invalid response code or smth')
                                                if not retry_flag:
                                                    retry_flag = True
                                                    time.sleep(1.5)
                                                    continue
                                                break
                                            except requests.exceptions.ConnectionError:
                                                print('Connection Error')
                                                break
                                            else:
                                                html = request.text
                                                tweet_info['tweet_html'] = json.loads(html)['html']
                                                time.sleep(1.5)
                                                break
                                        print(tweet_info['tweet_html'])
                                        tweets.append(tweet_info)

    with open('tweets.json', 'w') as file:
        json.dump(tweets, file)


if __name__ == '__main__':
    main()

