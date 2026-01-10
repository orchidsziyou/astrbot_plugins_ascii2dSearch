import re

from curl_cffi import requests
from bs4 import BeautifulSoup

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from astrbot.core.message.components import Plain, Reply, File, Nodes
from astrbot.api.message_components import Node, Plain, Image


def search_ascii2d(picture_url):
    # 1. 获取主页并提取令牌
    home_url = "https://ascii2d.net"
    session = requests.Session()
    response = session.get(home_url, impersonate="chrome110")
    soup = BeautifulSoup(response.text, 'html.parser')

    token_input = soup.find('input', {'name': 'authenticity_token'})
    if token_input:
        authenticity_token = token_input['value']
        print("获取到的令牌:", authenticity_token)
    else:
        raise Exception("未找到令牌！")

    url = picture_url
    params = {
        "utf8": "✓",
        "authenticity_token": authenticity_token,
        "uri": url
    }

    host = "https://ascii2d.net/"
    url_index = f"{host}/search/uri"
    response = session.post(url_index, timeout=30, data=params,
                            impersonate="chrome110")

    html_content = response.text

    soup = BeautifulSoup(html_content, 'html.parser')
    # 存储所有图片信息
    images_info = []
    # 查找所有的item-box
    for item in soup.find_all('div', class_='item-box'):
        img_info = {}

        # 提取图片信息
        img_box = item.find('div', class_='image-box')
        if img_box:
            img_tag = img_box.find('img')
            if img_tag and 'src' in img_tag.attrs:
                # 缩略图相对路径
                thumbnail_path = img_tag['src']
                # 转换为完整URL
                img_info['thumbnail'] = f"https://ascii2d.net{thumbnail_path}"

                # 从src中提取hash
                if 'thumbnail/' in thumbnail_path:
                    # 从类似 /thumbnail/c/7/3/3/c7338f09beb91f1b18d7be72ffd19e5c.jpg 中提取hash
                    hash_match = re.search(r'/([a-f0-9]{32})\.jpg', thumbnail_path)
                    if hash_match:
                        img_info['hash'] = hash_match.group(1)

        # 提取图片元数据
        info_box = item.find('div', class_='info-box')
        if info_box:
            # 获取hash
            hash_div = info_box.find('div', class_='hash')
            if hash_div:
                img_info['hash'] = hash_div.text.strip()

            # 获取尺寸和大小
            small_tag = info_box.find('small', class_='text-muted')
            if small_tag:
                img_info['size_info'] = small_tag.text.strip()

        # 提取链接信息
        detail_box = info_box.find('div', class_='detail-box') if info_box else None
        if detail_box:

            # 检查Pixiv链接
            pixiv_link = detail_box.find('a', href=re.compile(r'pixiv\.net'))
            if pixiv_link:
                img_info['source_url'] = pixiv_link['href']
                img_info['source'] = 'pixiv'
                img_info['title'] = pixiv_link.text.strip()

                # 获取作者链接
                author_link = pixiv_link.find_next('a')
                if author_link and 'users' in author_link.get('href', ''):
                    img_info['author_url'] = author_link['href']
                    img_info['author'] = author_link.text.strip()

            # 检查Twitter链接
            twitter_link = detail_box.find('a', href=re.compile(r'twitter\.com'))
            if twitter_link and twitter_link.get('href'):
                if 'status' in twitter_link['href']:
                    img_info['source_url'] = twitter_link['href']
                    img_info['source'] = 'twitter'
                    img_info['date'] = twitter_link.text.strip()

                    # 获取用户链接
                    user_link = twitter_link.find_next('a')
                    if user_link and 'i/user' in user_link.get('href', ''):
                        img_info['author_url'] = user_link['href']
                        img_info['author'] = user_link.text.strip()

            # 其他来源
            elif not pixiv_link and not twitter_link:
                # 可能是DLSite、DMM等其他来源
                for link in detail_box.find_all('a'):
                    if link.get('href'):
                        if 'dlsite' in link.get('href', ''):
                            img_info['source'] = 'dlsite'
                        elif 'dmm' in link.get('href', '').lower():
                            img_info['source'] = 'dmm'
                        elif 'amazon' in link.get('href', ''):
                            img_info['source'] = 'amazon'
                        elif 'fanza' in link.get('href', ''):
                            img_info['source'] = 'fanza'
                        else:
                            img_info['source'] = 'other'

                        img_info['source_url'] = link['href']
                        break

            # 提取外部链接
            external_div = detail_box.find('div', class_='external')
            if external_div:
                external_text = external_div.get_text(strip=True)
                img_info['external_info'] = external_text

                # 提取外部链接
                for ext_link in external_div.find_all('a'):
                    if 'dlsite' in ext_link.get('href', ''):
                        img_info['dlsite_url'] = ext_link['href']
                    elif 'dmm' in ext_link.get('href', '').lower():
                        img_info['dmm_url'] = ext_link['href']

        if img_info:  # 只添加有信息的内容
            images_info.append(img_info)

    return images_info


@register("ascii2dSoutu", "orchidsziyou", "一个简单的 通过ascii2d搜图的 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("search")
    async def search(self, event: AstrMessageEvent):
        message_chain = event.get_messages()
        mark = False
        is_picture = False
        botid = event.get_self_id()
        for msg in message_chain:
            if msg.type == 'Reply':
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                assert isinstance(event, AiocqhttpMessageEvent)
                client = event.bot
                payload = {
                    "message_id": msg.id
                }
                response = await client.api.call_action('get_msg', **payload)  # 调用 协议端  API
                reply_msg = response['message']
                for msg in reply_msg:
                    # print(msg)
                    if msg['type'] == 'image':
                        # 官方表情没办法保存
                        is_picture = True
                        picture_url = msg['data']['url']
                        print(picture_url)
                        images_info = search_ascii2d(picture_url)
                        if len(images_info) > 1:
                            #构造聊天记录节点
                            mark = True
                            All_node = []
                            info_node = Node(
                                uin=botid,
                                name="仙人",
                                content=[
                                    Plain("搜寻到的结果如下：")
                                ]
                            )
                            All_node.append(info_node)
                            for i, img in enumerate(images_info[1:], 2):  # 从第二个元素开始，索引从2开始
                                title = img.get('title', img.get('external_info', 'N/A'))
                                author = img.get('author', 'N/A')
                                source_url = img.get('source_url', 'N/A')
                                source = img.get('source', 'N/A')
                                node = Node(
                                    uin=botid,
                                    name="仙人",
                                    content=[
                                        Plain(f"{i-1}. "),
                                        Plain(f"\n标题：{title}\n作者：{author}\n来源：{source}\n链接：{source_url}")
                                    ]
                                )
                                All_node.append(node)

                                if i >6:
                                    break #最多显示6个结果

                            resNode = Nodes(
                                nodes=All_node
                            )
                            try:
                                yield event.chain_result([resNode])
                                return
                            except:
                                yield event.plain_result("发送失败")
                                return
        if not is_picture:
            yield event.plain_result("请回复图片")
        elif not mark:
            yield event.plain_result("没有找到结果")




