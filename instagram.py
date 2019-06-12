from asyncio import Semaphore
import asyncio
import re
import os

from bs4 import BeautifulSoup
from aiohttp import ClientSession


def create_path(obj: str, user_name: str, file_format: str) -> str:
    code = hash(obj)
    path = 'images/{}'.format(user_name)
    if not os.path.exists(path):
        os.makedirs(path)
    return '{}/{}.{}'.format(path, code, file_format)


async def get_user_id(user_name: str) -> int:
    url = 'https://www.instagram.com/{}/'.format(user_name)
    async with ClientSession() as session:
        async with session.get(url) as response:
            beautiful_soup = BeautifulSoup(await response.text(), "html.parser")
            script = beautiful_soup.find('script', string=re.compile('window._sharedData'))
            pattern = re.compile('"(\w+)":"(.*?)"')
            fields = dict(re.findall(pattern, script.text))
            return fields['id']


async def fetch(session: ClientSession, url: str, params: dict = None, return_format: str = 'json') -> dict or bytes:
    async with await session.get(url, params=params) as response:
        if return_format is 'json':
            ret = await response.json()
            return ret['data']['user']['edge_owner_to_timeline_media']
        if return_format is 'read':
            return await response.read()


async def download_photo(session: ClientSession, semaphore: Semaphore, resource: str, user_name: str, file_format: str):
    async with semaphore:
        with open(create_path(resource, user_name, file_format), 'wb') as file:
            file.write(await fetch(session, resource, return_format='read'))


async def get_photo(session: ClientSession, page_info: dict, user_name: str, tasks: dict = None) -> list:
    semaphore = Semaphore(50)
    posts = page_info['edges']
    if tasks is None:
        tasks = []
    for image in posts:
        node = image['node']
        if node['is_video']:
            resource = node['video_url']
            file_format = 'mp4'
        else:
            resource = node['display_resources'][2]['src']
            file_format = 'jpg'
        print(resource)
        task = asyncio.ensure_future(download_photo(session, semaphore, resource, user_name, file_format))
        tasks.append(task)
        if 'edge_sidecar_to_children' in node:
            tasks += await get_photo(session, node['edge_sidecar_to_children'], user_name)
    return tasks


async def pars(user_name: str) -> None:
    async with ClientSession() as session:
        url = 'https://www.instagram.com/graphql/query/'
        tasks = []

        try:
            params = {'query_hash': 'f2405b236d85e8296cf30347c9f08c2a',
                      'id': await get_user_id(user_name),
                      'first': 50}
        except KeyError:
            print('User not found or hidden')
            return None

        has_next_page = True
        while has_next_page:
            page_info: dict = await fetch(session, url, params)
            tasks += await get_photo(session, page_info, user_name)
            after = page_info['page_info']['end_cursor']
            has_next_page = page_info['page_info']['has_next_page']
            params['after'] = after

        responses = asyncio.gather(*tasks)
        await responses


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(pars(str(input('User: '))))
    loop.run_until_complete(future)
