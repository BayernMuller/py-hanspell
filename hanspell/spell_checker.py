# -*- coding: utf-8 -*-
"""
Python용 한글 맞춤법 검사 모듈
"""

import requests
import json
import time
import sys
import re
import os
from collections import OrderedDict
import xml.etree.ElementTree as ET
import logging

from . import __version__
from .response import Checked
from .constants import base_url
from .constants import CheckResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SpellChecker:
    TEST_TEXT = "바이에른 뮌헨은 최고최강입니다."
    TOKEN_FILE = 'token.txt'

    def __init__(self):
        self._agent = requests.Session()
        self.PY3 = sys.version_info[0] == 3
        self.token = None
        self._verify_token()
    
    def _verify_token(self):
        if os.path.exists(self.TOKEN_FILE):
            with open(self.TOKEN_FILE, 'r') as f:
                self.token = f.read().strip()
        else:
            self.token = self._get_token()
        
        try:
            self.check(self.TEST_TEXT)
        except Exception:
            self.token = self._get_token()
        
        with open(self.TOKEN_FILE, 'w') as f:
            f.write(self.token)

    def _get_token(self):
        url = "https://search.naver.com/search.naver?where=nexearch&sm=top_hty&fbm=0&ie=utf8&query=%EB%A7%9E%EC%B6%A4%EB%B2%95%EA%B2%80%EC%82%AC%EA%B8%B0"
        response = requests.get(url)

        if response.status_code == 200:
            html = response.text
            match = re.search(r'passportKey=([a-zA-Z0-9-_]+)', html)
            if match:
                passport_key = match.group(1)
                logger.debug("passportKey: %s", passport_key)
            else:
                logger.error("passportKey not found")
                exit(1)
        else:
            logger.error("Error: %s", response.status_code)
            exit(1)
        return passport_key

    def _remove_tags(self, text):
        text = u'<content>{}</content>'.format(text).replace('<br>','')
        if not self.PY3:
            text = text.encode('utf-8')

        result = ''.join(ET.fromstring(text).itertext())

        return result

    def check(self, text):
        """
        매개변수로 입력받은 한글 문장의 맞춤법을 체크합니다.
        """
        if isinstance(text, list):
            result = []
            for item in text:
                checked = self.check(item)
                result.append(checked)
            return result

        # 최대 500자까지 가능.
        if len(text) > 500:
            return Checked(result=False)

        payload = {
            'color_blindness': '0',
            'q': text,
            'passportKey': self.token
        }

        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.133 Safari/537.36',
            'referer': 'https://search.naver.com/',
        }

        start_time = time.time()
        r = self._agent.get(base_url, params=payload, headers=headers)
        passed_time = time.time() - start_time

        data = json.loads(r.text)
        html = data['message']['result']['html']
        result = {
            'result': True,
            'original': text,
            'checked': self._remove_tags(html),
            'errors': data['message']['result']['errata_count'],
            'time': passed_time,
            'words': OrderedDict(),
        }

        # 띄어쓰기로 구분하기 위해 태그는 일단 보기 쉽게 바꿔둠.
        # ElementTree의 iter()를 써서 더 좋게 할 수 있는 방법이 있지만
        # 이 짧은 코드에 굳이 그렇게 할 필요성이 없으므로 일단 문자열을 치환하는 방법으로 작성.
        html = html.replace('<em class=\'green_text\'>', '<green>') \
                .replace('<em class=\'red_text\'>', '<red>') \
                .replace('<em class=\'violet_text\'>', '<violet>') \
                .replace('<em class=\'blue_text\'>', '<blue>') \
                .replace('</em>', '<end>')
        items = html.split(' ')
        words = []
        tmp = ''
        for word in items:
            if tmp == '' and word[:1] == '<':
                pos = word.find('>') + 1
                tmp = word[:pos]
            elif tmp != '':
                word = u'{}{}'.format(tmp, word)
            
            if word[-5:] == '<end>':
                word = word.replace('<end>', '')
                tmp = ''

            words.append(word)

        for word in words:
            check_result = CheckResult.PASSED
            if word[:5] == '<red>':
                check_result = CheckResult.WRONG_SPELLING
                word = word.replace('<red>', '')
            elif word[:7] == '<green>':
                check_result = CheckResult.WRONG_SPACING
                word = word.replace('<green>', '')
            elif word[:8] == '<violet>':
                check_result = CheckResult.AMBIGUOUS
                word = word.replace('<violet>', '')
            elif word[:6] == '<blue>':
                check_result = CheckResult.STATISTICAL_CORRECTION
                word = word.replace('<blue>', '')
            result['words'][word] = check_result

        result = Checked(**result)

        return result
